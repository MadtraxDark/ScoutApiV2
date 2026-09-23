# SDD Progress Ledger — Camoufox + Visão VIP reliability

Branch: main (in-place; dirty tree includes ADR 0038 WIP — worktree skipped)
Plan: docs/superpowers/plans/2026-09-23-camoufox-visaovip-reliability.md
Note: Do NOT git commit unless user explicitly asks (user rule).

## Tasks

Task 0: complete — baseline Docker C1
Task 1: complete — BrowserScheduler C1 (review clean after fixes)
Task 2: complete — claim_trial half-open
Task 3: complete — attempt budgets
Task 4: complete — redis ProfileLock proven + wired
Task 5: complete — C1/C2/C3 measured (incomplete third-store)
Task 6: complete — ADR 0039; capacity=1 adjudicated
Task 7: complete — S25 incomplete_hydrate vs B650M OK
Task 8: complete — Server Action GO (deploy-coupled ID)
Task 9: complete — Strategy A behind flag
Task 10: complete — A→B chain + taxonomy
Task 11: complete — store+capability circuit
Task 12: complete — chaos/soak unit suite
Task 13: complete — multi-cat regressions (KaBuM live; VV docker-exec perm caveat)
Task 14: complete — docs + PENDING-018 + final report

## Adjudications

- Capacity production = 1 (C1) despite Task 5 C2 recommendation (reliability-first)
- Strategy A flag default false until PENDING-018 discovery wiring

## Remaining open

- PENDING-016, PENDING-017 (pre-existing Shopee/ML)
- PENDING-018 (Strategy A action-id discovery wiring)
