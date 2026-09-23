"""Process-wide Camoufox/browser infrastructure health + circuit breaker.

Launch failures (missing binary, profile I/O, Playwright launch timeout) are
structural: once the browser cannot start, repeating the same launch for every
store/query wastes minutes. Page navigation timeouts must NOT open this circuit.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from scout_api.modules.crawler.core.exceptions import RequestError

# Structural browser codes — never map to Product Match NO_MATCH.
BROWSER_INFRASTRUCTURE_ERROR_CODES: frozenset[str] = frozenset(
    {
        "BROWSER_LAUNCH_ERROR",
        "BROWSER_INFRASTRUCTURE_UNAVAILABLE",
    }
)

_LAUNCH_FAILURE_MARKERS: tuple[str, ...] = (
    "launch_persistent_context",
    "browsertype.launch",
    "failed to launch",
    "executable doesn't exist",
    "no such file or directory",
    "input/output error",
    "i/o error",
    "camoufox-bin",
)


class BrowserHealthState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class BrowserCircuitBreaker:
    """Shared circuit for structural Camoufox launch failures."""

    def __init__(self, *, threshold: int = 1, cooldown_seconds: int = 60) -> None:
        self.threshold = max(1, threshold)
        self.cooldown_seconds = max(1, cooldown_seconds)
        self._failures = 0
        self._state = BrowserHealthState.HEALTHY
        self._opened_at: datetime | None = None
        self._lock = threading.Lock()
        self.launch_failures = 0
        self.circuit_open_count = 0

    @property
    def state(self) -> BrowserHealthState:
        with self._lock:
            self._maybe_half_open_unlocked()
            return self._state

    def allow(self, now: datetime | None = None) -> bool:
        with self._lock:
            self._maybe_half_open_unlocked(now)
            return self._state != BrowserHealthState.UNAVAILABLE

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._state = BrowserHealthState.HEALTHY
            self._opened_at = None

    def record_launch_failure(self, now: datetime | None = None) -> None:
        with self._lock:
            self.launch_failures += 1
            self._failures += 1
            if self._failures >= self.threshold:
                if self._state != BrowserHealthState.UNAVAILABLE:
                    self.circuit_open_count += 1
                self._state = BrowserHealthState.UNAVAILABLE
                self._opened_at = now or datetime.now(UTC)

    def _maybe_half_open_unlocked(self, now: datetime | None = None) -> None:
        if self._state != BrowserHealthState.UNAVAILABLE or self._opened_at is None:
            return
        current = now or datetime.now(UTC)
        if current >= self._opened_at + timedelta(seconds=self.cooldown_seconds):
            # Probe window: allow one launch attempt.
            self._state = BrowserHealthState.DEGRADED

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            self._maybe_half_open_unlocked()
            return {
                "state": self._state.value,
                "failures": self._failures,
                "launch_failures": self.launch_failures,
                "circuit_open_count": self.circuit_open_count,
                "opened_at": self._opened_at.isoformat() if self._opened_at else None,
            }


_breaker: BrowserCircuitBreaker | None = None
_breaker_lock = threading.Lock()


def get_browser_circuit(
    *,
    threshold: int | None = None,
    cooldown_seconds: int | None = None,
) -> BrowserCircuitBreaker:
    """Return the process-wide browser circuit (lazy singleton)."""
    global _breaker
    with _breaker_lock:
        if _breaker is None:
            fail_threshold = threshold
            cooldown = cooldown_seconds
            if fail_threshold is None or cooldown is None:
                try:
                    from scout_api.core.config import get_settings

                    settings = get_settings()
                    if fail_threshold is None:
                        fail_threshold = settings.browser_circuit_failure_threshold
                    if cooldown is None:
                        cooldown = settings.browser_circuit_cooldown_seconds
                except Exception:  # noqa: BLE001
                    fail_threshold = fail_threshold if fail_threshold is not None else 1
                    cooldown = cooldown if cooldown is not None else 60
            _breaker = BrowserCircuitBreaker(
                threshold=fail_threshold,
                cooldown_seconds=cooldown,
            )
        return _breaker


def reset_browser_circuit_for_tests() -> None:
    """Drop the singleton so unit tests start from a clean circuit."""
    global _breaker
    with _breaker_lock:
        _breaker = None


def is_browser_launch_failure(exc: BaseException) -> bool:
    """True when ``exc`` indicates Camoufox/Playwright failed to start."""
    name = type(exc).__name__.casefold()
    message = str(exc).casefold()
    # Navigation / page timeouts are NOT launch failures.
    if "page.goto" in message or ("waiting for" in message and "navigat" in message):
        return False
    if any(marker in message for marker in _LAUNCH_FAILURE_MARKERS):
        return True
    if "timeouterror" in name and any(
        marker in message for marker in ("launch", "browser", "persistent", "browsertype")
    ):
        return True
    # Playwright launch TimeoutError is often just "Timeout 45000ms exceeded."
    if name == "timeouterror" and "exceeded" in message:
        if "page." in message or "waiting for" in message:
            return False
        return True
    return False


def classify_browser_error(exc: BaseException, *, url: str) -> RequestError:
    """Map a structural browser failure to a RequestError code."""
    if is_browser_launch_failure(exc):
        return RequestError(
            f"Falha ao iniciar o browser (Camoufox/Playwright): {exc}",
            code="BROWSER_LAUNCH_ERROR",
            url=url,
            retryable=False,
        )
    return RequestError(
        f"Infraestrutura de browser indisponível: {exc}",
        code="BROWSER_INFRASTRUCTURE_UNAVAILABLE",
        url=url,
        retryable=False,
    )


def browser_unavailable_error(*, url: str) -> RequestError:
    """Fast-fail when the browser circuit is open."""
    return RequestError(
        "Browser Camoufox indisponível (circuit open após falha estrutural de launch)",
        code="BROWSER_INFRASTRUCTURE_UNAVAILABLE",
        url=url,
        retryable=False,
    )


def is_browser_infrastructure_error(code: str | None) -> bool:
    return bool(code) and code in BROWSER_INFRASTRUCTURE_ERROR_CODES
