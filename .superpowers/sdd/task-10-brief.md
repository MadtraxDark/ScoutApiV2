### Task 10: Phase 10 — Strategy B fallback + error taxonomy

**Files:**
- Modify: `store_search_service.py`, `visaovip.py`, `browser_health.py` consumers, Match error mapping
- Modify: frontend-facing message maps if any in API schemas
- Test: unit taxonomy + strategy chain

- [ ] **Step 1: Prefer new codes; map legacy `UPSTREAM_BLOCKED` on read only**

- [ ] **Step 2: Chain A→B; all blocked → ERROR `SEARCH_INCOMPLETE_RESPONSE` or `UPSTREAM_WAF_BLOCKED`; genuine zero → empty candidates**

- [ ] **Step 3: Ensure UI path never returns raw snake_case as user message**

- [ ] **Step 4: pytest PASS**

**Rollback:** feature flag off Strategy A; alias map keeps old clients working.

---
