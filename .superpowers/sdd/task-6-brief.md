### Task 6: Phase 6 — Capacity decision + ADR

**Files:**
- Update: `docs/adr/0032-...` only via **new** ADR if needed (never silent flip)
- Possibly create: `docs/adr/0039-bounded-browser-scheduler.md`
- Update: `docs/adr/README.md`, `AGENTS.md` (short invariant), `.cursor/rules/` short rule if durable

- [ ] **Step 1: If C1 wins — ADR emend/new documenting scheduler+queue+lock; keep capacity=1; ADR 0032 pool rejection stands**

- [ ] **Step 2: If C2/C3 wins — new ADR superseding 0032’s “reject N browsers” clause with evidence + isolated profiles; set default capacity**

- [ ] **Step 3: Set production default Settings to decided capacity**

**Rollback:** force `CAMOUFOX_BROWSER_CAPACITY=1`.

---
