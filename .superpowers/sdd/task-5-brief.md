### Task 5: Phase 5 — Capacity C1 / C2 / C3 benchmark

**Files:**
- Complete: `scripts/bench_camoufox_capacity.py`
- Update working log with tables

**Must measure per config:** success/fail, launch fail, nav fail, circuit opens, queue_wait, launch/nav latency, p50/p95/max, throughput, CPU, memory, firefox processes, launch/reuse/recycle counts, timeouts, lock errors.

Layer1 infra + Layer2 Visão VIP SERP + one other browser store. Same image/env.

- [ ] **Step 1: Implement harness with `--capacity 1|2|3` creating isolated `slot-*` dirs**

- [ ] **Step 2: Run C1, C2, C3; store JSON results under `memory/working/`**

- [ ] **Step 3: Apply acceptance rule; write DECISION paragraph**

**Rollback:** N/A measurement.

---
