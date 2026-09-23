### Task 4: Phase 4 — Cross-process profile ownership

**Files:**
- Create: `src/scout_api/modules/crawler/core/profile_lock.py`
- Modify: `browser_slot.py` / scheduler acquire path
- Test: `tests/unit/test_profile_lock.py`
- Create: `scripts/probe_profile_lock_multiprocess.py`

**Decision gate (must run before locking implementation choice):**

1. On **real** `./data/camoufox-profiles` bind (Docker Desktop Windows): Process A holds lock; B cannot acquire same profile.
2. Kill -9 Process A; measure time until B can acquire (crash release).
3. If file lock unreliable on bind → use Redis SET NX PX pattern from `DistributedSingleFlight` (TTL + compare-and-delete) as primary for profile lease; keep lock file as best-effort secondary.

- [ ] **Step 1: Write probe script + record results in working log `PROFILE_LOCK_PROOF`**

- [ ] **Step 2: Implement chosen locker behind `ProfileLock` protocol**

```python
class ProfileLock(Protocol):
    def acquire(self, profile_path: Path, *, timeout_ms: int) -> ProfileLockLease: ...
    def release(self, lease: ProfileLockLease) -> None: ...
```

- [ ] **Step 3: Scheduler acquire: slot path → ProfileLock → then warm session**

- [ ] **Step 4: Unit tests + script PASS on project volume**

**Rollback:** `CAMOUFOX_PROFILE_LOCK=off` (dev only; warn in logs).

---
