# Task 14 — Relatório Final: Docs / ADR / Wrap-up
# Camoufox + Visão VIP Reliability (2026-09-23)

---

## 1. Pesquisa

**Problema original:** instabilidade de fetch com Camoufox em produção (fila
ilimitada, sem lock de perfil, half-open sem singleflight, sem budgets por store).
Para Visão VIP: causa de `UPSTREAM_BLOCKED` no S25 Ultra não isolada; apenas
Strategy B (browser SERP) disponível.

**Pesquisa conduzida (Tasks 0–8):**

- Playwright docs + issues (#19742): mesmo `user_data_dir` não pode ser aberto
  por múltiplos processos; valida ProfileLock.
- Camoufox issues #185/#314: concorrência + Docker → deadlocks resolvidos em
  versões recentes; semáforos ajudam.
- OSS: camoufox-connector, camofox-browser, Scraping Central browser-pool
  patterns → bounded scheduler com fila FIFO + isolamento de perfil por slot.
- Circuit half-open: gunnargrosch#7 (thundering herd) → `claim_trial()` atômico.
- Visão VIP: probe A/B (Task 7) isolou `incomplete_hydrate` no S25 Ultra
  (B650M hidrata 3/3; S25 0/3, DOM 114 KB sem cards).
- Server Action (Task 8): endpoint `searchProducts` funcional, sem session gate;
  Action ID deploy-coupled (rotaciona em cada build) → discovery obrigatória.

---

## 2. Camoufox

**Implementado (Tasks 1–6):**

| Componente | Arquivo | Função |
|---|---|---|
| `BrowserScheduler` | `crawler/core/browser_scheduler.py` | Fila FIFO limitada; `BROWSER_QUEUE_SATURATED` |
| `BrowserSlot` | `crawler/core/browser_slot.py` | Slot isolado + context lifecycle |
| `ProfileLock` | `crawler/core/profile_lock.py` | Redis primary / fcntl fallback / NullProfileLock |
| `FailureDomains` | `crawler/core/failure_domains.py` | Circuit por store key |
| `claim_trial()` | `crawler/core/browser_health.py` | Token atômico HALF_OPEN |
| `StoreAttemptBudget` | `matching/attempt_budget.py` | queries / external / browser_nav |

**Benchmark C1/C2/C3 (Task 5):**

| Config | L1 throughput Δ | L2 throughput Δ | L2 erros | P95 Δ (L2) |
|---|---|---|---|---|
| C1 | baseline | baseline | 0/5 | baseline |
| C2 | +116% | +48% | **1/10** | +9.7% |
| C3 | +204% | +144% | 0/15 | +15.4% |

**Decisão C1 (Task 6 — adjudicação do controller):**
C2 L2 = 90% success rate < 100% C1. Regra RELIABILITY > throughput → **C1 permanece**.
ADR 0039 criado e aceito.

**Testes:** `tests/unit/test_browser_scheduler.py`, `test_browser_circuit_claim_trial.py`,
`test_profile_lock.py`, `test_attempt_budget.py`, `test_browser_health.py`.

---

## 3. Visão VIP

**Root cause S25 Ultra (probe Task 7):**
`incomplete_hydrate` — shell Next.js (~114 KB) carrega, mas RSC client-side não
popula cards `/prod/` dentro do settle_ms configurado. Não é WAF/infra (B650M
funciona no mesmo container/sessão). Causa exata não confirmada (RSC mais lento
para smartphones, genuine empty sem marcador, ou throttling assimétrico CF).

**Strategy B (atual):** browser SERP Camoufox com settle. Funciona para B650M,
GPU, CPU, SSD. **Falha para S25 Ultra (0 candidatos).**

**Strategy A (Task 9–11, implementada atrás de flag):**
HTTP POST direto ao `searchProducts` Server Action → JSON sem RSC hydration.
- Código: `visaovip_action_strategy.py` + `VisaoVipSearchAdapter.try_strategy_a()`.
- Sem session gate. Cloudflare não bloqueia o POST.
- **Pendência:** `Next-Action` ID é deploy-coupled. Discovery automática (Camoufox
  intercept ou chunk scan) não foi wired no fluxo de produção. Flag `enabled=False`.
  → **PENDING-018** (P2).

**Classify empty atualizado:** `incomplete_hydrate` → `classify_empty_result()`
retorna `"incomplete"` (não `NO_MATCH`); proteção de circuit evita retries infinitos.

**Regression multi-categoria (Task 13):** PASS — phone/MB/CPU/GPU/RAM/SSD KaBuM;
store bloqueada não trava Run; isolamento search Visão VIP ≠ PDP confirmado;
circuito em produção = healthy.

---

## 4. Product Match

**Contratos afetados:**

- `StoreAttemptBudget` integrado ao `ProductMatchService` (loop por store).
- Defaults: `MATCH_SEARCH_QUERY_BUDGET=5`, `MATCH_EXTERNAL_ATTEMPT_BUDGET=12`,
  `MATCH_BROWSER_NAVIGATION_BUDGET=8`.
- Strategy A + B na mesma query = 1 `begin_query()`; cada request upstream = 1
  `record_external()`. Cache hits = `skip_cached()`.
- `stopped_reason` preservado no log por store (observabilidade).
- `docs/matching/README.md` atualizado com contratos de budget + BrowserScheduler.

---

## 5. Implementation

**Docs atualizados nesta Task 14:**

| Arquivo | O que mudou |
|---|---|
| `docs/crawler/stores/visaovip.md` | Strategy A/B, incomplete_hydrate S25, limitações |
| `docs/matching/README.md` | StoreAttemptBudget + BrowserScheduler contratos |
| `.cursor/rules/browser-scheduler-bounded.mdc` | Regra nova: C1 + ProfileLock + claim_trial + multi-strategy |
| `docs/pending/PENDING-018-...md` | Criada: Strategy A ID discovery |
| `docs/pending/README.md` | PENDING-018 adicionado ao índice ativo |
| `memory/working/2026-09-23-...md` | Before/after final ambas as trilhas |

**ADRs:** ADR 0039 presente e correto desde Task 6; não requer emenda.
ADR 0037 (launch health + fail-fast): presente e correto.
ADR 0038 (PDP/Search split): presente e correto.

**Regra `.cursor/rules/`:** `browser-scheduler-bounded.mdc` criada cobrindo
C1 invariante, ProfileLock, claim_trial, failure domains e multi-strategy fallback.

**`AGENTS.md`:** invariante de C1 já presente desde Task 6. Sem nova adição necessária.

---

## Pendências restantes

- **PENDING-018** (P2, OPEN): Visão VIP Strategy A — wiring de ID discovery
  (Camoufox intercept ou chunk scan) em produção. Flag permanece `enabled=False`
  até implementação e teste com query S25 Ultra.
- **PENDING-016** (P1, OPEN): Shopee wall-time no Match full-store (pré-existente).
- **PENDING-017** (P1, OPEN): Reativar ML/Shopee após login estável (pré-existente).

Nenhuma regressão de performance introduzida nesta fase de documentação.
