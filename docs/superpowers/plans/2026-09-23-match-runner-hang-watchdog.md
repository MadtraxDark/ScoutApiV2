# Match-runner Hang Watchdog — Implementation Plan

> **For agentic workers:** execute task-by-task without intermediate approval. TDD.

**Goal:** Uma MatchRun travada nunca bloqueia o match-runner indefinidamente.

**Architecture:** ProgressTracker (monotonic) + store/run wall deadlines + daemon watchdog com `os._exit(78)` + Docker restart/reclaim ADR 0036.

**Tech Stack:** Python 3.12, SQLAlchemy, pytest, Docker Compose.

## Global Constraints

- Heartbeat ≠ progress
- Timeout → ERROR/FAILED, nunca NO_MATCH/COMPLETED
- Settings via `core/config.py` (0 = disabled)
- Sem mudar Camoufox/navegação além de propagar remaining timeout

## Tasks

### Task 1: ProgressTracker + constants + settings
- Create `matching/match_progress.py`, `matching/match_hang_constants.py`
- Settings + validation
- Tests: progress vs heartbeat, thread safety, one-exit, graceful shutdown race

### Task 2: Watchdog daemon
- Wire into `match_run_worker.run_forever` / `process_claimed_run`
- Inject `exit_func` for tests

### Task 3: Store + run wall deadlines
- Cooperative checks in `product_match_service.process_one`
- Propagate `min(op_timeout, remaining)` where APIs allow
- Partial results preserved

### Task 4: Docs + .env.example + ADR 0036 amendment
### Task 5: Docker hard-hang + Run B recovery validation
