"""Unit tests for MatchRun progress tracker and hang watchdog (TDD)."""

from __future__ import annotations

import threading

import pytest

from scout_api.modules.matching.match_hang_constants import (
    FAILURE_CODE_RUN_WALL_TIMEOUT,
    FAILURE_CODE_STORE_WALL_TIMEOUT,
    MATCH_WORKER_HANG_EXIT_CODE,
)
from scout_api.modules.matching.match_progress import (
    MatchProgressPhase,
    MatchProgressTracker,
)
from scout_api.modules.matching.match_watchdog import MatchHangWatchdog


def test_hang_exit_code_is_documented_constant() -> None:
    assert MATCH_WORKER_HANG_EXIT_CODE == 78


def test_failure_codes_are_structured_not_messages() -> None:
    assert FAILURE_CODE_STORE_WALL_TIMEOUT == "STORE_WALL_TIMEOUT"
    assert FAILURE_CODE_RUN_WALL_TIMEOUT == "RUN_WALL_TIMEOUT"


def test_progress_tracker_mark_and_age() -> None:
    clock = {"t": 1000.0}

    def mono() -> float:
        return clock["t"]

    tracker = MatchProgressTracker(monotonic=mono)
    tracker.arm(run_id="run-a", worker_id="w1")
    tracker.mark_progress(
        run_id="run-a",
        store="kabum",
        phase=MatchProgressPhase.SEARCHING,
    )
    clock["t"] = 1010.0
    snap = tracker.snapshot()
    assert snap is not None
    assert snap.run_id == "run-a"
    assert snap.store == "kabum"
    assert snap.phase == MatchProgressPhase.SEARCHING
    assert snap.progress_age_seconds == pytest.approx(10.0)


def test_disarm_clears_active_run() -> None:
    tracker = MatchProgressTracker()
    tracker.arm(run_id="run-a", worker_id="w1")
    tracker.mark_progress(run_id="run-a", phase=MatchProgressPhase.STARTING_STORE)
    tracker.disarm(run_id="run-a")
    assert tracker.snapshot() is None


def test_mark_progress_ignores_other_run_id() -> None:
    tracker = MatchProgressTracker()
    tracker.arm(run_id="run-a", worker_id="w1")
    tracker.mark_progress(run_id="run-a", phase=MatchProgressPhase.SEARCHING)
    first = tracker.snapshot()
    assert first is not None
    first_mono = first.last_progress_monotonic
    tracker.mark_progress(run_id="run-other", phase=MatchProgressPhase.MATCHING)
    second = tracker.snapshot()
    assert second is not None
    assert second.last_progress_monotonic == first_mono
    assert second.phase == MatchProgressPhase.SEARCHING


def test_watchdog_does_not_treat_heartbeat_as_progress() -> None:
    """Lease renewal must NOT reset the stale clock."""
    clock = {"t": 0.0}
    exits: list[int] = []
    expired: list[str] = []

    def mono() -> float:
        return clock["t"]

    tracker = MatchProgressTracker(monotonic=mono)
    tracker.arm(run_id="run-a", worker_id="w1")
    tracker.mark_progress(run_id="run-a", phase=MatchProgressPhase.SEARCHING)

    wd = MatchHangWatchdog(
        tracker=tracker,
        stale_seconds=10.0,
        check_interval_seconds=1.0,
        enabled=True,
        monotonic=mono,
        exit_func=lambda code: exits.append(code),
        sleep_func=lambda _s: None,
        expire_lease_func=lambda rid: expired.append(rid),
    )
    clock["t"] = 5.0
    # Simulate lease heartbeat without progress.
    tracker.note_lease_heartbeat()  # must be a no-op for progress age
    clock["t"] = 11.0
    wd.check_once()
    assert exits == [MATCH_WORKER_HANG_EXIT_CODE]
    assert expired == ["run-a"]


def test_watchdog_no_fire_when_progress_continues() -> None:
    clock = {"t": 0.0}
    exits: list[int] = []

    def mono() -> float:
        return clock["t"]

    tracker = MatchProgressTracker(monotonic=mono)
    tracker.arm(run_id="run-a", worker_id="w1")
    tracker.mark_progress(run_id="run-a", phase=MatchProgressPhase.SEARCHING)

    wd = MatchHangWatchdog(
        tracker=tracker,
        stale_seconds=10.0,
        check_interval_seconds=1.0,
        enabled=True,
        monotonic=mono,
        exit_func=lambda code: exits.append(code),
        sleep_func=lambda _s: None,
    )
    for t in (3.0, 6.0, 9.0):
        clock["t"] = t
        tracker.mark_progress(run_id="run-a", phase=MatchProgressPhase.EVALUATING)
        wd.check_once()
    clock["t"] = 12.0
    wd.check_once()
    assert exits == []


def test_watchdog_fires_once_only() -> None:
    clock = {"t": 0.0}
    exits: list[int] = []

    def mono() -> float:
        return clock["t"]

    tracker = MatchProgressTracker(monotonic=mono)
    tracker.arm(run_id="run-a", worker_id="w1")
    tracker.mark_progress(run_id="run-a", phase=MatchProgressPhase.SEARCHING)

    wd = MatchHangWatchdog(
        tracker=tracker,
        stale_seconds=5.0,
        check_interval_seconds=0.1,
        enabled=True,
        monotonic=mono,
        exit_func=lambda code: exits.append(code),
        sleep_func=lambda _s: None,
    )
    clock["t"] = 6.0
    wd.check_once()
    wd.check_once()
    wd.check_once()
    assert exits == [MATCH_WORKER_HANG_EXIT_CODE]


def test_watchdog_skips_when_disarmed_before_fire() -> None:
    clock = {"t": 0.0}
    exits: list[int] = []

    def mono() -> float:
        return clock["t"]

    tracker = MatchProgressTracker(monotonic=mono)
    tracker.arm(run_id="run-a", worker_id="w1")
    tracker.mark_progress(run_id="run-a", phase=MatchProgressPhase.SEARCHING)

    wd = MatchHangWatchdog(
        tracker=tracker,
        stale_seconds=5.0,
        check_interval_seconds=0.1,
        enabled=True,
        monotonic=mono,
        exit_func=lambda code: exits.append(code),
        sleep_func=lambda _s: None,
    )
    clock["t"] = 6.0
    tracker.disarm(run_id="run-a")
    wd.check_once()
    assert exits == []


def test_watchdog_skips_during_graceful_shutdown() -> None:
    clock = {"t": 0.0}
    exits: list[int] = []

    def mono() -> float:
        return clock["t"]

    tracker = MatchProgressTracker(monotonic=mono)
    tracker.arm(run_id="run-a", worker_id="w1")
    tracker.mark_progress(run_id="run-a", phase=MatchProgressPhase.SEARCHING)

    wd = MatchHangWatchdog(
        tracker=tracker,
        stale_seconds=5.0,
        check_interval_seconds=0.1,
        enabled=True,
        monotonic=mono,
        exit_func=lambda code: exits.append(code),
        sleep_func=lambda _s: None,
    )
    clock["t"] = 6.0
    wd.request_shutdown()
    wd.check_once()
    assert exits == []


def test_watchdog_disabled_never_fires() -> None:
    clock = {"t": 0.0}
    exits: list[int] = []

    def mono() -> float:
        return clock["t"]

    tracker = MatchProgressTracker(monotonic=mono)
    tracker.arm(run_id="run-a", worker_id="w1")
    tracker.mark_progress(run_id="run-a", phase=MatchProgressPhase.SEARCHING)

    wd = MatchHangWatchdog(
        tracker=tracker,
        stale_seconds=1.0,
        check_interval_seconds=0.1,
        enabled=False,
        monotonic=mono,
        exit_func=lambda code: exits.append(code),
        sleep_func=lambda _s: None,
    )
    clock["t"] = 100.0
    wd.check_once()
    assert exits == []


def test_watchdog_stale_zero_disabled() -> None:
    clock = {"t": 0.0}
    exits: list[int] = []

    def mono() -> float:
        return clock["t"]

    tracker = MatchProgressTracker(monotonic=mono)
    tracker.arm(run_id="run-a", worker_id="w1")
    tracker.mark_progress(run_id="run-a", phase=MatchProgressPhase.SEARCHING)

    wd = MatchHangWatchdog(
        tracker=tracker,
        stale_seconds=0.0,
        check_interval_seconds=0.1,
        enabled=True,
        monotonic=mono,
        exit_func=lambda code: exits.append(code),
        sleep_func=lambda _s: None,
    )
    clock["t"] = 100.0
    wd.check_once()
    assert exits == []


def test_deadline_remaining_and_expired() -> None:
    from scout_api.modules.matching.match_deadlines import MonotonicDeadline

    clock = {"t": 100.0}

    def mono() -> float:
        return clock["t"]

    dl = MonotonicDeadline.start(timeout_seconds=10.0, monotonic=mono)
    assert dl.remaining_seconds() == pytest.approx(10.0)
    clock["t"] = 105.0
    assert dl.remaining_seconds() == pytest.approx(5.0)
    assert not dl.expired()
    clock["t"] = 111.0
    assert dl.expired()
    assert dl.remaining_seconds() == 0.0


def test_deadline_zero_means_disabled() -> None:
    from scout_api.modules.matching.match_deadlines import MonotonicDeadline

    dl = MonotonicDeadline.start(timeout_seconds=0.0)
    assert dl.disabled
    assert not dl.expired()
    assert dl.remaining_seconds() is None


def test_operation_timeout_capped_by_remaining() -> None:
    from scout_api.modules.matching.match_deadlines import capped_timeout_seconds

    assert capped_timeout_seconds(180.0, remaining=40.0) == 40.0
    assert capped_timeout_seconds(30.0, remaining=40.0) == 30.0
    assert capped_timeout_seconds(30.0, remaining=None) == 30.0


def test_progress_tracker_thread_safe_marks() -> None:
    tracker = MatchProgressTracker()
    tracker.arm(run_id="run-a", worker_id="w1")
    errors: list[BaseException] = []

    def worker(i: int) -> None:
        try:
            for _ in range(50):
                tracker.mark_progress(
                    run_id="run-a",
                    store=f"s{i}",
                    phase=MatchProgressPhase.EVALUATING,
                )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert errors == []
    assert tracker.snapshot() is not None
