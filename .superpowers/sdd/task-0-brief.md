### Task 0: Phase 0 — Baseline / reproduction

**Files:**
- Create/Update: `memory/working/2026-09-23-camoufox-visaovip-reliability.md`
- Create: `scripts/bench_camoufox_capacity.py` (skeleton metrics only)
- Test: N/A (measurement)

**Interfaces:**
- Produces: baseline numbers for C1 (current code) before changes: launch/reuse/fail counts, P50/P95 of a small nav set, RSS sample

- [ ] **Step 1: Record versions**

Run in container:

```bash
docker compose exec match-runner python -c "import camoufox, playwright; print(camoufox.__version__ if hasattr(camoufox,'__version__') else 'n/a'); import importlib.metadata as m; print('playwright', m.version('playwright'))"
```

Log binary/path if available. Append to working log under `CAMOUFOX_RELIABILITY / baseline`.

- [ ] **Step 2: Minimal infra baseline (current capacity=1 behavior)**

Run 10 sequential warm fetches against a cheap stable URL used today (or store origin warmup). Record `browser_launch` / `browser_reuse` observes if already emitted.

- [ ] **Step 3: Confirm process topology**

Document in working log: Search Match = `match-runner`; PDP refresh = `monitor`; shared volume = `./data/camoufox-profiles`. Do **not** start distributed store circuit yet.

- [ ] **Step 4: Commit** (only if user asked) — otherwise leave uncommitted until user requests.

**Rollback:** N/A (read-only).

---
