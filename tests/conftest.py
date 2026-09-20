import os

import pytest
from fastapi.testclient import TestClient

from scout_api.core.config import get_settings
from scout_api.core.performance import (
    BUDGETS,
    OperationCategory,
    category_for_pytest_item,
    observe,
)
from scout_api.core.rate_limit import reset_rate_limiter
from scout_api.main import app


@pytest.fixture(autouse=True)
def _default_test_security_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Existing integration/unit HTTP tests run with auth optional (non-production).

    Security suite re-enables AUTH_REQUIRED=true explicitly.
    """
    if os.environ.get("SCOUT_SECURITY_TESTS") == "1":
        yield
        return
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    get_settings.cache_clear()
    reset_rate_limiter()
    yield
    get_settings.cache_clear()
    reset_rate_limiter()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[object]):
    """Emit slow_operation for tests that exceed category budgets."""
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not hasattr(report, "duration"):
        return
    duration_ms = float(report.duration) * 1000
    category = category_for_pytest_item(item)
    observe(
        "pytest",
        duration_ms,
        category=category,
        stage=report.when,
        context={
            "nodeid": item.nodeid,
            "outcome": report.outcome,
        },
    )


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter,
    exitstatus: int,
    config: pytest.Config,
) -> None:
    """Print a compact slow-test section after --durations (or alone)."""
    del exitstatus, config
    reported = getattr(terminalreporter, "stats", {})
    durations: list[tuple[float, str]] = []
    for key in ("passed", "failed", "skipped", "error", "xfailed", "xpassed"):
        for rep in reported.get(key, []):
            if getattr(rep, "when", None) != "call":
                continue
            duration = float(getattr(rep, "duration", 0.0) or 0.0)
            if duration <= 0:
                continue
            durations.append((duration, getattr(rep, "nodeid", "?")))
    if not durations:
        return
    durations.sort(reverse=True)
    unit_budget = BUDGETS[OperationCategory.UNIT_TEST]
    slow = [
        (secs, nodeid)
        for secs, nodeid in durations
        if secs * 1000 >= unit_budget.warn_ms
    ]
    terminalreporter.write_sep("=", "ScoutApiV2 slow tests (budget-aware)")
    if not slow:
        terminalreporter.write_line(
            f"Nenhum teste acima do WARN unit ({unit_budget.warn_ms}ms). "
            f"Top: {durations[0][1]} = {durations[0][0]:.3f}s"
        )
        return
    for secs, nodeid in slow[:25]:
        terminalreporter.write_line(f"{secs:8.3f}s  {nodeid}")
