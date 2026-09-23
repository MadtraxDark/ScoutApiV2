### Task 12: Phase 12 — Integration / load / soak / chaos

**Files:**
- Tests under `tests/unit` + scripts chaos
- Working log before/after metrics

Chaos checklist (each must leave MatchRun terminal; no false NO_MATCH):

- [ ] browser process killed
- [ ] launch timeout
- [ ] owner-thread failure simulated
- [ ] profile lock held by peer
- [ ] queue full
- [ ] store WAF block
- [ ] operation nav timeout
- [ ] Server Action invalid contract (if A enabled)

Soak: reuse/recycle/memory/profile/queue/circuit for decided capacity until evidence enough (minutes, not hours blindly).

**Coverage gate:** compare eligible/attempted stores, candidates, PDPs, MATCH/NO_MATCH/ERROR — reject “faster” if coverage silently dropped.

---
