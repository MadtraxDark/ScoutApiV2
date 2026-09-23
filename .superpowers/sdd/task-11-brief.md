### Task 11: Phase 11 — Store + capability circuit

**Files:**
- Create: `src/scout_api/modules/crawler/core/store_capability_health.py`
- Wire: `store_search_service.py` (search), **not** PDP spider path for search failures
- Test: unit isolation search vs product_scrape; NO_RESULTS does not trip; WAF repeated does

Process-local initially (Match Search ≈ match-runner). Document if api/monitor later run Search.

- [ ] **Step 1: Implement claim_trial same semantics as infra; separate state**

- [ ] **Step 2: Wire search failures with `failure_domain=store_capability`**

- [ ] **Step 3: Prove PDP scrape still works when search circuit OPEN (unit/integration)**

**Rollback:** `STORE_CAPABILITY_CIRCUIT_ENABLED=false`.

---
