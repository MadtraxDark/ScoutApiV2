# Design: Camoufox bounded reliability + Visão VIP multi-strategy discovery

Date: 2026-09-23  
Status: **APPROVED** (com ajustes do aprovador, 2026-09-23)  
Choice: **B** — measure capacity 1 vs 2 vs 3 with fully isolated profiles; adopt N only if evidence says so.

Priority order for capacity decision:

```text
RELIABILITY → COVERAGE → PREDICTABLE LATENCY → THROUGHPUT
```

Spec aprovado. Implementação só após aprovação do plano em
`docs/superpowers/plans/2026-09-23-camoufox-visaovip-reliability.md`.

---

## Approved decisions (binding)

### Half-open / claim_trial (infra + store-capability)

```text
CLOSED  → execução normal
OPEN    → fail-fast
cooldown expirado → HALF_OPEN/DEGRADED
primeiro caller que claim_trial() → UMA probe real
demais callers enquanto probe em andamento → FAIL-FAST (não esperam)
```

Requisitos:

- `claim_trial()` atômico; uma probe por circuit/failure-domain
- sucesso → fecha/reset; falha → reabre + reinicia cooldown
- cancelamento/crash da probe **não** deixa HALF_OPEN eterno (lease/TTL/finally)
- unit tests com fake clock; teste de concorrência: 10 callers → 1 probe
- mesma semântica conceitual para store+capability; estado **não** compartilhado com infra

### Budgets (separados; não um contador ambíguo)

| Conceito | Semântica | Default inicial |
|---|---|---|
| `SEARCH_QUERY_BUDGET` | **Máximo** de queries distintas por store/MatchRun — **não** obrigação de executar N | `5` (Settings) |
| `EXTERNAL_REQUEST_ATTEMPT_BUDGET` | Requests que realmente saíram para upstream | configurável |
| `BROWSER_NAVIGATION_BUDGET` | Navegações reais Camoufox | configurável |

Regras:

- Progressive search: query1 → evidência suficiente? **parar**; senão query2… até o teto
- Cache hit / query dedup → **não** consome attempt externo
- Strategy A + B na mesma query = **1** query; attempts externos separados
- Proxy fallback real consome attempt correspondente
- Observabilidade por store: `queries_used`, `queries_budget`, `external_attempts`,
  `external_attempt_budget`, `browser_navigations`, `browser_navigation_budget`,
  `stopped_reason`
- Não hardcode `5` em múltiplos arquivos — só Settings

### Capacity

- Default permanece `capacity=1` até benchmark
- C1 vs C2 vs C3 com profiles isolados obrigatório
- Aprovação deste design **≠** aprovação de capacity>1
- Critério N>1 inalterado (≥15% P95 **ou** ≥20% throughput **e** sem piora de reliability)

### Queue

- `capacity` + `queue_capacity` + `queue_timeout`
- Fila saturada → falha controlada (não growth silencioso)
- Métricas: `queue_depth`, `queue_capacity`, `queue_wait_ms`, `queue_timeout_count`
- Cancelamento: job CANCELLED sai da fila; **não** navega depois

### Fairness

- Política: **FIFO por job de browser** (simples, previsível)
- Mitigação de monopolização: budgets de browser-nav / candidate scrape por store
  (já no Match) + capacity=1 serializa naturalmente; se capacity>1, FIFO continua
  suficiente — não round-robin complexo sem evidência

### Visão VIP

- Root cause A/B S25 vs B650M **antes** de Strategy A
- Server Action só após contrato real + contract detection
- Sem fake multi-strategy (só A+B se A validada)
- Genuine NO_RESULTS **não** abre store circuit

### Process topology (evidência compose)

- `match-runner`: Product Match Search + PDP scrape da Run
- `api`: crawl/refresh sob demanda; Match worker **off** no compose padrão
- `monitor`: Offer Refresh / PDP
- **Todos** montam `./data/camoufox-profiles` (bind Windows host → container)

⇒ Profile ownership **cross-process obrigatório**.  
⇒ Store Search circuit: Match Search é sobretudo `match-runner` → process-local
  suficiente **inicialmente**; não implementar distributed store circuit por hipótese.
  Browser infra + profile lock **devem** funcionar entre api/monitor/match-runner.

---

## 1. Current State

### Camoufox / fetch

| Piece | Reality |
|---|---|
| Fetcher stack | HTTP-first wrappers → `StoreAwareHtmlFetcher` → Camoufox direct (+ proxied) → urllib |
| Warm session | `_WarmBrowserSession`: 1 persistent context per `CamoufoxHtmlFetcher` |
| Owner thread | `_PlaywrightOwnerLoop` serializes Playwright sync API |
| Concurrency | Implicit capacity=1; Match workers still serialize on Camoufox |
| Queue | Unbounded; no wait timeout; no queue_capacity |
| Profiles | locale + direct/proxied; **no cross-process lock** |
| Circuit | Launch-only; `DEGRADED` without atomic claim_trial |
| ADR 0032 | Rejected N parallel browsers |

### Visão VIP Search

Single `/busca/termo/` + Camoufox DOM. HTTP shell incomplete for **all** categories.
Server Action `searchProducts` evidenced but contract not captured. S25 ERROR root
cause not closed.

---

## 2. Research Findings

(Ver versão anterior + Playwright user_data_dir, Camoufox #185/#314, circuit
claimTrial, stdlib flock vs Redis vs PG advisory.)

**Profile lock choice (pending real-env proof in Phase 4):**

| Option | Verdict |
|---|---|
| Python mutex only | Insufficient |
| stdlib `fcntl`/`msvcrt` lock file | Primary **candidate** — must prove on **actual** `./data/camoufox-profiles` bind mount |
| Redis SET NX PX (já no projeto) | Fallback se file lock falhar no bind; TTL evita órfão eterno |
| PG advisory | Rejected for browser lifetime (connection pool) |

---

## 3. Camoufox Failure Model

```text
BROWSER_INFRASTRUCTURE
STORE_CAPABILITY(store, capability)
SINGLE_OPERATION
```

Observabilidade obrigatória:

```text
failure_domain=browser_infrastructure
failure_domain=store_capability store=visaovip capability=search
failure_domain=operation store=visaovip operation=search_query
```

---

## 4. BrowserScheduler Design

### Slot identity (diagnóstico)

Cada slot expõe (em memória / logs; persistência opcional):

```text
slot_id, profile_path, owner, state, started_at, last_used_at, fetch_count, health
```

Toda operação browser loga `slot_id`.

### Capacity / queue / timeouts

| Setting | Role |
|---|---|
| `CAMOUFOX_BROWSER_CAPACITY` | Slots ativos (default 1) |
| `CAMOUFOX_BROWSER_QUEUE_CAPACITY` | Máx jobs esperando |
| `CAMOUFOX_QUEUE_TIMEOUT_MS` | Espera por slot |
| `CAMOUFOX_LAUNCH_TIMEOUT_MS` | Launch |
| `CAMOUFOX_TIMEOUT_MS` | Navigation |

Saturação de fila → `BROWSER_INFRASTRUCTURE_UNAVAILABLE` (ou código específico
`BROWSER_QUEUE_SATURATED`) controlado.

### Profiles

```text
{base}/direct/slot-{id}/locale_{slug}/
{base}/proxied/slot-{id}/...
```

Nunca compartilhar `user_data_dir` entre owners simultâneos.

### Fairness

**FIFO** na fila do scheduler. Justificativa: simples, previsível, testável;
budgets por store evitam monopolização de Match; evitar RR até evidência.

### Cancellation

Job com cancel flag / MatchRun `cancelled` → remove da fila; se já em execução,
abort nav quando seguro; **nunca** iniciar nav após cancel.

### Lifecycle

CREATE → HEALTHY → REUSE → RECYCLE → CLOSE; POISON → CLOSE → CREATE.

---

## 5. Circuit Breaker Design

### Infra

OPEN fail-fast; HALF_OPEN com `claim_trial` atômico; non-holders fail-fast;
probe lease/TTL + `finally` para não travar HALF_OPEN.

### Store + capability

Mesma semântica; chaves `(store, capability)`; Search ≠ product_scrape.

**NÃO abre em:** genuine NO_RESULTS, matcher rejection, ProductIdentity conflict,
PARSE_ERROR isolado sem evidência de upstream.

**Pode abrir em:** WAF, connection reset, incomplete response **repetida**
comprovadamente upstream.

---

## 6. Retry / attempt budgets

Progressive stop + tetos separados (query / external / browser-nav).

### Worst-case external requests (Visão VIP Search, após caps)

| Case | Queries | Strategies/query | External attempts | Browser navs |
|---|---|---|---|---|
| Best | 1 | A success | 1 | 0 |
| Normal fallback | 1 | A fail → B | ≤2 | 1 |
| Worst allowed | ≤5 | A→B each | ≤10 (+ proxy ≤+5 se policy) | ≤5 |

Proxy: no máximo **1** fallback por attempt chain, contado no external budget.
Settle/captcha: Match fail-fast após 1 resolve falho (ADR 0032) — não ×12 no Match.

Candidate PDP scrapes: budget separado (`max_candidates_per_store`), não multiplica
`SEARCH_QUERY_BUDGET`.

---

## 7. Capacity Benchmark Plan

C1/C2/C3; metrics completas (p50/p95/max, queue_wait, throughput, CPU, memory,
processes, launch/reuse/recycle, timeouts, circuit opens). Critério N>1 inalterado.
Soak após escolha. Default fica 1 se empate/instabilidade.

---

## 8. Visão VIP Root-Cause Investigation

**Obrigatório antes de Strategy A:** A/B S25 vs B650M mesmo container/config/browser health.

Capturar por operação: query, URL, slot, profile, HTTP status, final URL, nav/settle,
DOM size, `/prod/` links, challenge markers, network failures, Server Action requests,
duration.

Categoria ≠ causa.

---

## 9. Visão VIP Candidate Discovery Design

Só A (`searchProducts` se contrato válido) + B (Camoufox SERP).  
Contract detection: resposta inválida / action ID quebrado → strategy unavailable → B;
**nunca** NO_MATCH falso.  
Sem autocomplete/sitemap/local index sem evidência.

---

## 10. Error Taxonomy (migração controlada)

Novos códigos preferenciais:

- `BROWSER_LAUNCH_ERROR`, `BROWSER_INFRASTRUCTURE_UNAVAILABLE`, `BROWSER_QUEUE_SATURATED`
- `UPSTREAM_WAF_BLOCKED`, `UPSTREAM_CONNECTION_RESET`
- `SEARCH_INCOMPLETE_RESPONSE`, `SEARCH_PARSE_ERROR`
- Genuine empty → outcome NO_RESULTS / candidatos vazios (não ERROR)

`UPSTREAM_BLOCKED`: **legacy alias** em leitura/logs antigos; **não** novo output preferencial.

UI: nunca snake_case cru.

---

## 11–14. Tests / Migration / ADR / Risks

(Ver plano de implementação para checklist executável.)

ADR 0032: não supersede antes do benchmark.  
Riscos externos: WAF, action ID churn, empty real, bind-mount lock semantics.

---

## Open items resolved by approver

1. Half-open non-probe → **fail-fast** ✓  
2. `search_query_budget=5` = teto configurável ✓  
3. Spec aprovado com ajustes ✓  
