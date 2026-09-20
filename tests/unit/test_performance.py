"""Unit tests for performance observability budgets and events."""

from __future__ import annotations

import logging

import pytest

from scout_api.core.performance import (
    BUDGETS,
    DuplicateWorkTracker,
    OperationCategory,
    RetryLedger,
    Severity,
    classify_severity,
    format_stage_summary,
    observe,
    timed,
)


def test_budgets_cover_all_categories() -> None:
    assert set(BUDGETS) == set(OperationCategory)


def test_classify_severity_thresholds() -> None:
    budget = BUDGETS[OperationCategory.UNIT_TEST]
    assert classify_severity(budget.expected_ms, budget) is Severity.NORMAL
    assert classify_severity(budget.warn_ms, budget) is Severity.WARN
    assert classify_severity(budget.slow_ms, budget) is Severity.SLOW
    assert classify_severity(budget.critical_ms, budget) is Severity.CRITICAL


def test_observe_silent_when_normal(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="scout_api.core.performance"):
        event = observe(
            "fast_op",
            10.0,
            category=OperationCategory.UNIT_TEST,
        )
    assert event.severity is Severity.NORMAL
    assert "slow_operation" not in caplog.text
    assert "operation_timing" not in caplog.text


def test_observe_warns_when_slow(caplog: pytest.LogCaptureFixture) -> None:
    budget = BUDGETS[OperationCategory.UNIT_TEST]
    with caplog.at_level(logging.INFO, logger="scout_api.core.performance"):
        event = observe(
            "slow_unit",
            float(budget.slow_ms),
            category=OperationCategory.UNIT_TEST,
            stage="call",
            context={"test": "demo"},
        )
    assert event.severity is Severity.SLOW
    assert "slow_operation" in caplog.text
    assert "slow_unit" in caplog.text


def test_timed_context_records_duration() -> None:
    with timed("demo", category=OperationCategory.HTTP_REQUEST) as bag:
        bag["status"] = "ok"
    assert bag["duration_ms"] >= 0
    assert bag["status"] == "ok"


def test_retry_ledger_exposes_attempt_timings() -> None:
    ledger = RetryLedger(operation="http_get")
    ledger.begin_attempt()
    ledger.end_attempt(outcome="timeout", code="TIMEOUT", backoff_ms=2000)
    ledger.begin_attempt()
    ledger.end_attempt(outcome="success")
    ctx = ledger.as_context()
    assert ctx["retries"] == 1
    assert ctx["attempts"] == 2
    assert ctx["backoff_ms_total"] == 2000.0
    assert len(ctx["attempt_timings"]) == 2


def test_duplicate_work_tracker_logs_repeats(caplog: pytest.LogCaptureFixture) -> None:
    tracker = DuplicateWorkTracker()
    assert tracker.record("url", "https://example.com/a") == 1
    assert tracker.record("url", "https://example.com/a") == 2
    with caplog.at_level(logging.WARNING, logger="scout_api.core.performance"):
        tracker.observe_if_repeated()
    assert "duplicate_work" in caplog.text


def test_format_stage_summary() -> None:
    text = format_stage_summary(
        "Product Match",
        11800,
        {
            "kabum": {"search_ms": 900, "scrape_ms": 1200},
            "aliexpress": 5700.0,
        },
    )
    assert "Product Match: 11.8s" in text
    assert "kabum:" in text
    assert "aliexpress: 5.700s" in text


def test_observe_redacts_sensitive_context(caplog: pytest.LogCaptureFixture) -> None:
    budget = BUDGETS[OperationCategory.HTTP_REQUEST]
    with caplog.at_level(logging.INFO, logger="scout_api.core.performance"):
        event = observe(
            "http_get",
            float(budget.warn_ms),
            category=OperationCategory.HTTP_REQUEST,
            context={"authorization": "Bearer secret-token", "store": "kabum"},
        )
    redacted = event.as_log_dict()
    assert redacted["context"]["authorization"] == "***"
    assert "secret-token" not in caplog.text
    assert redacted["context"]["store"] == "kabum"
