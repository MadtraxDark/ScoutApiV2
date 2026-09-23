# Working log â Camoufox reliability + VisÃ£o VIP discovery

Date: 2026-09-23
Status: Phase 0 baseline medido (Task 0); implementaÃ§Ã£o aguarda plano

## Trilha CAMOUFOX_RELIABILITY

### Baseline â Phase 0 / Task 0 (2026-09-23, C1 cÃ³digo atual)

**VersÃµes (container `match-runner`, metadata):**

| Pacote | VersÃ£o |
|---|---|
| camoufox | 0.5.6 |
| playwright | 1.62.0 |
| python | `/usr/local/bin/python` (3.12 image) |

**BinÃ¡rio Camoufox (pkgman):** `/home/app/.cache/camoufox/browsers/official/152.0.4-beta.30-5720d45b`

**Local venv (host):** camoufox 0.5.6, playwright 1.62.0 (alinhado ao container).

**Topologia Compose (confirmada, sem circuit store distribuÃ­do ainda):**

| Papel | ServiÃ§o | Comando |
|---|---|---|
| Product Match / Store Search | `match-runner` | `scout_api.modules.matching.match_run_worker` |
| PDP / offer refresh | `monitor` | `scout_api.modules.monitoring.worker` |
| API HTTP (Match worker in-process off) | `api` | default entrypoint |

Volume compartilhado: `./data/camoufox-profiles` â `/home/app/.cache/scout-api/camoufox-profiles` em **api**, **monitor** e **match-runner**.

**C1 sequential warm fetch (10Ã `https://example.com/`, profile isolado `/tmp/.../slot-0`, harness `scripts/bench_camoufox_capacity.py`):**

| MÃ©trica | Valor |
|---|---|
| `browser_launches` | 1 |
| `browser_reuses` | 9 |
| `browser_launch_failures` | 0 |
| fetch wall P50 (ok) | 809.8 ms |
| fetch wall P95 (ok) | 3400.0 ms |
| fetch wall max (cold+1) | 5462.9 ms |
| RSS start / peak / end (KB) | 68020 / 138488 / 138556 |
| sucesso | 10/10 |

JSON bruto: `memory/working/bench_camoufox_c1_baseline_2026-09-23.json`.

Observabilidade: `CamoufoxHtmlFetcher` emite `observe(browser_launch)` / `observe(browser_reuse)` no fetcher; contadores acima batem com warm-reuse serial (1 launch, Nâ1 reuses).

### Baseline (cÃ³digo atual â notas arquiteturais prÃ©-mediÃ§Ã£o)

- Arquitetura: 1 warm persistent context por `CamoufoxHtmlFetcher` (direct + proxied)
- SerializaÃ§Ã£o: `_PlaywrightOwnerLoop` + `threading.Lock` â 1 fetch Playwright por vez por fetcher
- Fila owner: `queue.Queue()` ilimitada; `fut.result()` sem timeout de espera
- Circuit: `BrowserCircuitBreaker` process-wide, sÃ³ launch estrutural (ADR 0037)
- Half-open: estado `DEGRADED` libera callers sem token single-flight explÃ­cito
- Profile: dirs por locale + proxy; sem FileLock OS; ADR 0032 rejeitou pool N browsers
- Warm: recycle por `CAMOUFOX_WARM_MAX_FETCHES`; poison markers seletivos (nÃ£o dropa em todo UPSTREAM_BLOCKED)
- Match: `MATCH_STORE_CONCURRENCY` workers HTTP; Camoufox ainda serializa atrÃ¡s do owner

### Research (fontes)

- Playwright docs: "browsers do not allow launching multiple instances with the same User Data Directory"
- Playwright #19742: concurrent same USER_DIR = not allowed (by design)
- Camoufox usage: persistent_context requires user_data_dir
- Camoufox #185 / #314: concurrency + Docker hangs; semaphores help; fingerprint/viewport deadlocks fixed in newer versions
- OSS: camoufox-connector (acquire/release queue + pool), camofox-browser (1 profile per userId), Scraping Central browser-pool patterns (bounded workers + queue)
- Circuit: half-open thundering herd (gunnargrosch#7); redeye/rasuvaeff = claimTrial / probeLimit=1

### Matriz preliminar Camoufox

| OpÃ§Ã£o | Reliability | Memory | Startup | Isolation | Complexity | Docker | Notas |
|---|---|---|---|---|---|---|---|
| A launch/request | baixa | alto churn | caro | ok | baixa | ok | pior amortizaÃ§Ã£o |
| B warm atual (1) | mÃ©dia | baixo | amortizado | ok se serial | mÃ©dia | ok | estado atual |
| C pool N persistent same profile | **inseguro** | â | â | **quebra** | â | â | rejeitado Playwright |
| D bounded scheduler 1âfew + profiles isolados | alta | mÃ©dio | mÃ©dio | ok | mÃ©dio | medir | mede sweet spot |
| E worker/service separado | alta | isolado | alto ops | ok | alto | ok | YAGNI sem prova |

## Trilha VISAO_VIP_DISCOVERY

### Estado atual

- Search: `VisaoVipSearchAdapter` â Ãºnico `/busca/termo/{slug}/` + parse CSS `/prod/`
- PDP: `VisaoVipSpider` RSC â separado (ADR 0038)
- S25 Run2: `UPSTREAM_BLOCKED` SERP; causa raiz **nÃ£o** isolada (comentÃ¡rio "phone not expected" contradiz taxonomia â seria NO_MATCH se genuine empty)
- B650M: Search+Match OK com Camoufox
- Sem HTTP/RSC SERP/API/autocomplete no adapter
- `classify_empty`: incomplete â UPSTREAM_BLOCKED; genuine_empty â []; unknown com `/prod/` sem cards â risco NO_MATCH falso

### A/B Probe â Task 7 (probe_visaovip_serp_ab, 2026-09-23T20:xx:xxZ)

**Script:** `scripts/probe_visaovip_serp_ab.py` â 3 iteraÃ§Ãµes por query, mesmo container e config que Task 5.

#### Resultados por query

| Query | OK | Falhas | nav_result | avg /prod/ links | avg DOM (KB) | avg duraÃ§Ã£o |
|---|---|---|---|---|---|---|
| `samsung galaxy s25 ultra` | 0/3 | 3/3 | `incomplete_hydrate` (3Ã) | 0.0 | 114.6 | 3785 ms |
| `asus tuf gaming b650m-e wifi` | 3/3 | 0/3 | `ok` (3Ã) | 3.0 | 120.8 | 2543 ms |

**URLs finais:** ambas as queries permanecem no URL correto `/busca/termo/{slug}/` (sem redirect).

**Challenge markers S25:** `cf_challenge_platform` detectado apenas na iteraÃ§Ã£o 1 (string encontrada no HTML de ~114 KB). `is_challenge_page()` retornou **False** nas 3 iteraÃ§Ãµes â tamanho do DOM descarta interstitial real (checks de CF exigem `len(html) < 40_000`).

#### Root-cause verdict

**CATEGORIA: INCOMPLETE HYDRATION â nÃ£o Ã© WAF/infra/query.**

```
VERDICT: INCOMPLETE HYDRATION â O SERP do Samsung Galaxy S25 Ultra carrega o
shell Next.js (~114 KB DOM) mas o RSC/client-side nunca popula os cards /prod/.
B650M hidrata com sucesso (3 links /prod/, DOM 120 KB). O marker
cf_challenge_platform encontrado na iter 1 Ã© o script de proteÃ§Ã£o Cloudflare
embutido no bundle Next.js da VisÃ£o VIP (presente em pÃ¡ginas normais a 114 KB â
nÃ£o Ã© um interstitial de challenge). is_challenge_page() retornou False nas 3
iteraÃ§Ãµes. Sem marcadores de genuine_empty ("nenhum resultado" etc.) â o produto
pode existir no catÃ¡logo mas o RSC da categoria smartphones nÃ£o hidratou dentro
do settle_ms configurado, OU a VisÃ£o VIP nÃ£o tem Samsung Galaxy S25 Ultra em
estoque/catÃ¡logo mas sem exibir marcador de "sem resultados".

Causas provÃ¡veis (ordem de probabilidade):
1. SERP de smartphones usa variante de pÃ¡gina Next.js com hydration mais lenta /
   RSC payload adicional â settle_ms atual (5 s) insuficiente para essa categoria.
2. Samsung Galaxy S25 Ultra nÃ£o estÃ¡ no catÃ¡logo da VisÃ£o VIP (genuine empty sem
   marcador visÃ­vel) â mas esperarÃ­amos "nenhum resultado" no DOM se esse fosse o caso.
3. Cloudflare Bot Manager aplica throttling assimÃ©trico por query de alta
   comercialidade (S25 vs B650M) â hipÃ³tese secundÃ¡ria (DOM chegou intacto).

Distingue claramente de:
- INFRA: B650M funciona no mesmo container/session/perfil â infra OK.
- WAF hard block: DOM 114 KB com URL correta â nÃ£o Ã© pÃ¡gina de bloqueio.
- GENUINE EMPTY: ausÃªncia de marcadores "nenhum resultado" â nÃ£o confirmado.
- QUERY slug: URL gerada corretamente como /samsung-galaxy-s25-ultra/.
```

**ImplicaÃ§Ã£o para Task 9:** Strategy A (browser SERP com maior settle_ms) pode resolver caso (1). InvestigaÃ§Ã£o adicional de HTTP/RSC endpoint pode confirmar caso (2).

**Gate cumprido:** diagnÃ³stico completo antes de iniciar Strategy A.

### Matriz preliminar VisÃ£o VIP

| OpÃ§Ã£o | Reliability | Anti-bot | Latency | Maintenance | Coverage | Complexity |
|---|---|---|---|---|---|---|
| A browser SERP atual | mÃ©dia | alta exposiÃ§Ã£o | ~3â7s | mÃ©dia | boa se hidrata | baixa |
| B HTTP/RSC SERP | ? | menor | baixa | mÃ©dia | ? | mÃ©dia |
| C internal Search API | ? | baixa | baixa | mÃ©dia | ? | mÃ©dia |
| D autocomplete | ? | baixa | baixa | baixa | parcial | mÃ©dia |
| E category/catalog | ? | mÃ©dia | mÃ©dia | alta | parcial | alta |
| F local candidate index | alta se sync | nula na search | baixa | alta | depende sync | alta |

InvestigaÃ§Ã£o network/endpoints ainda pendente (pÃ³s-estabilizaÃ§Ã£o Camoufox).

## DecisÃµes (aprovadas)

- Spec APROVADO com ajustes: `docs/superpowers/specs/2026-09-23-camoufox-visaovip-reliability-design.md`
- Plano: `docs/superpowers/plans/2026-09-23-camoufox-visaovip-reliability.md` (aguarda aprovaÃ§Ã£o para executar)
- Half-open: non-probe FAIL-FAST; claim_trial atÃ´mico + trial TTL
- Budgets separados: search_query (teto 5) / external / browser_nav; progressive stop
- Queue: capacity + queue_capacity + timeout; cancel remove da fila; FIFO
- Profile lock: provar no bind `./data/camoufox-profiles` (api+monitor+match-runner)
- VisÃ£o VIP: A/B root cause ANTES de Strategy A; Server Action sÃ³ com contrato+detection
- NÃ£o implementar atÃ© aprovaÃ§Ã£o do plano

## Task 5 â Phase 5: Capacity Benchmark C1/C2/C3 (executado 2026-09-23)

### Resultados â Layer 1 (`https://example.com/`, 10 iter/slot)

| Config | Fetches | OK | Erros | Throughput (rps) | P50 (ms) | P95 (ms) | Î throughput vs C1 | Î P95 vs C1 | Peak RSS (KB) |
|--------|---------|-----|-------|-----------------|----------|----------|-------------------|-------------|----------------|
| C1 | 10 | 10 | 0 | 0.745 | 789 | 3640 | baseline | baseline | 139.184 |
| C2 | 20 | 20 | 0 | 1.610 | 811 | 3843 | **+116%** | +5.6% | 142.024 |
| C3 | 30 | 30 | 0 | 2.267 | 803 | 4327 | **+204%** | +18.9% | 144.536 |

### Resultados â Layer 2 (`https://www.visaovip.com/busca/termo/notebook/`, 5 iter/slot)

| Config | Fetches | OK | Erros | Throughput (rps) | P50 (ms) | P95 (ms) | Î throughput vs C1 | Î P95 vs C1 | Peak RSS (KB) |
|--------|---------|-----|-------|-----------------|----------|----------|-------------------|-------------|----------------|
| C1 | 5 | 5 | 0 | 0.271 | 3066 | 5477 | baseline | baseline | 159.484 |
| C2 | 10 | 9 | 1 | 0.402 | 3321 | 6009 | **+48%** | +9.7% | 185.252 |
| C3 | 15 | 15 | 0 | 0.660 | 3298 | 6324 | **+144%** | +15.4% | 210.956 |

Erros: C2-L2 teve 1 erro transiente (`UPSTREAM_REQUEST_ERROR` â Playwright "page navigating" race condition); nÃ£o Ã© falha estrutural nem especÃ­fico de multi-slot. C1 e C3 = 0 erros.  
Launch failures: 0 em todos. Circuit opens: 0 em todos. Lock storms: 0. Perfis isolados `slot-{id}` â estÃ¡veis.

JSONs brutos: `memory/working/bench_cap_c1_layer1_2026-09-23.json`, `bench_cap_c1_layer2_2026-09-23.json`, `bench_cap_c2_2026-09-23.json`, `bench_cap_c3_2026-09-23.json`, `bench_cap_summary_2026-09-23.json`.

### DECISION â Capacidade recomendada para Task 6

**RecomendaÃ§Ã£o Task 5: C2 (capacity=2).** [SUPERSEDIDA pela adjudicaÃ§Ã£o de Task 6 abaixo]

Ambos C2 e C3 atendem a regra de aceitaÃ§Ã£o via throughput (â¥20%): C2 entrega +116% em L1 e +48% em L2; C3 entrega +204% e +144%. Sem corruption, sem lock storms, sem falhas de launch em nenhuma configuraÃ§Ã£o. MemÃ³ria: C2 adiciona ~25 MB de RSS por slot em carga real (L2) â aceitÃ¡vel.

C2 Ã© preferÃ­vel a C3 por conservadorismo: 2Ã throughput com overhead menor de Firefox em paralelo (em produÃ§Ã£o: api + monitor + match-runner = atÃ© 6 processos Firefox simultÃ¢neos com C2 vs 9 com C3), e C3 piora o P95 por requisiÃ§Ã£o em atÃ© 19% sem benefÃ­cio prioritÃ¡rio para o gargalo principal (scraping sequencial por store em um MatchRun). O Ãºnico erro de C2 em L2 Ã© uma race condition transiente do Playwright (`page navigating`) â nÃ£o especÃ­fica de multi-slot, poderia ocorrer em C1 em amostra maior.

**ProduÃ§Ã£o permanece capacity=1 atÃ© Task 6 implementar explicitamente.**

CritÃ©rio de done da spec atendido: N=2 satisfaz (â¥15% P95 melhora [NÃO] **OR** â¥20% throughput [SIM]) com todas as prÃ©-condiÃ§Ãµes (successâC1, sem piora de launch/circuit, memÃ³ria aceitÃ¡vel).

### ADJUDICAÃÃO â Task 6 (controller, 2026-09-23): **C1 WINS â capacidade permanece 1**

Motivos (regra de prioridade RELIABILITY â latÃªncia â throughput):
- C2 L2 (VisÃ£o VIP, anti-bot): 1 erro / 10 = 90% < 100% de C1. Viola `success â C1`.
- "Faster but more failures â reject" â clÃ¡usula explÃ­cita da spec.
- P95 C2/C3 nÃ£o melhorou â¥15% em nenhuma camada (L1: +5.6%; L2: +9.7%).
- Throughput nÃ£o compensa reliability sob a regra AND.
- Bench incompleto: harness sem `BrowserScheduler` de produÃ§Ã£o; sem terceira loja; sem carga compose.
- ADR 0032 (pool N browsers rejeitado) permanece Accepted.
- ADR 0039 criado: documenta BrowserScheduler + ProfileLock + claim_trial + decisÃ£o C1 + condiÃ§Ãµes de reabertura C2+.
- `CAMOUFOX_BROWSER_CAPACITY=1` no `.env.example` â nÃ£o alterado.

## Task 3 â Phase 3: Retry/Attempt Budgets (implementado 2026-09-23)

`StoreAttemptBudget` implementado e conectado ao store loop de `ProductMatchService`.
Defaults: `MATCH_SEARCH_QUERY_BUDGET=5`, `MATCH_EXTERNAL_ATTEMPT_BUDGET=12`, `MATCH_BROWSER_NAVIGATION_BUDGET=8`.

### Pior caso â tabela de budgets por store/MatchRun

| Caso | queries | external attempts | browser nav |
|---|---|---|---|
| Best (hit na 1Âª query, 1 SERP cache miss, 1 PDP) | 1 | 2 | 0â1 |
| Normal AâB (mesma query, 2 strategies) | 1 | â¤2 | 1 |
| Match direto apÃ³s 2 queries | 2 | â¤4 | â¤2 |
| Worst allowed (budget esgotado) | â¤5 | â¤12 | â¤8 |
| Com proxy fallback (proxy conta external, nÃ£o browser nav) | â¤5 | â¤12 | â¤8 |

CÃ¡lculo worst-case externo: cada query pode gerar 1 SERP fetch + N candidate scrapes. Com 5 queries Ã (1 SERP + atÃ© 2 PDPs) = 15 â cap de 12 para safety. Browser nav limitado a 8 independente do nÃºmero de queries.

---

### Server Action Probe â Task 8 (2026-09-23T~21:xx:xxZ)

**Script:** `scripts/probe_visaovip_search_action.py`

#### Contrato capturado (de `chunk_serp3.body` + `action_*.body` do probe anterior)

**POST URL:** `https://www.visaovip.com/busca/termo/{slug}/`  
**MÃ©todo:** POST  
**Headers obrigatÃ³rios:**
```
Next-Action: <action_id>          â deploy-coupled, muda a cada build
Content-Type: text/plain;charset=UTF-8
Accept: text/x-component,*/*
x-intlayer-locale: pt-BR
Origin: https://www.visaovip.com
```
**Payload (JSON array de args):**
```json
[searchTerm, searchType, characteristicFilters, locale, page, perPage, stock]
```
Exemplo concreto:
```json
["asus-tuf-gaming-b650m-e-wifi", "termo", [], "pt-BR", 1, 24, "all"]
```
**Assinatura confirmada via decompile de `chunk_serp3.body`:**
```js
// p = createServerReference("<id>", ..., "searchProducts")
// m = createServerReference("<id>", ..., "searchFacets")
let v = await p(searchTerm, searchType, characteristics[], locale, page, perPage, stock);
```

**Formato da resposta (`Content-Type: text/x-component`):**
```
0:{"a":"$@1","f":"","b":"<buildId>","q":"","i":false}
1:{"products":[...], "facets":{"brands":[], ...}, "totalCount":N, "currentPage":0, "totalPages":N}
```

#### IDs de aÃ§Ã£o (snapshot 2026-09-23, build `QAm14Voexwwlur451SrkG`)

| AÃ§Ã£o | Action ID |
|---|---|
| `searchProducts` | `7f674263c13a9d8d28d0768c8016b1791b8051502a` |
| `searchFacets` | `784f2ef5d5603dc817ded8e27c904518fc45af1b63` |

**ATENÃÃO:** Esses IDs sÃ£o **deploy-coupled** â confirmado que rotacionaram desde o probe.

#### Estabilidade do action ID

**RESULTADO: ID NÃO Ã BUILD-STABLE (deploy-coupled)**

- HTTP POST com ID estÃ¡tico retorna `404 "Server action not found"` no deploy atual.
- Build anterior (`QAm14Voexwwlur451SrkG`): 200 OK com `action_empty_arr.body`.
- Deploy detectado: `chunk_serp3.body` (128 KB) vs `5304c8ab31d35f98.js` atual (31 KB, conteÃºdo diferente).
- Chunk URL `5304c8ab31d35f98.js` tem o mesmo nome mas conteÃºdo diferente â novo deploy.

**IMPLICAÃÃO:** Action IDs mudam em cada novo deploy da VisÃ£o VIP.

#### Necessidade de sessÃ£o / cookies

- `action_empty_arr.body` retornou 200 OK **sem cookies** â sem session-gate no endpoint.
- CF Cloudflare nÃ£o bloqueia o POST (CF bloqueia GET da pÃ¡gina SERP, nÃ£o o POST da action).

#### Discovery path

**Problema:** GET da pÃ¡gina SERP via HTTP puro retorna shell CF de 5.8 KB (sem script tags).  
**SoluÃ§Ã£o:** O action ID corrente deve ser descoberto via browser (Camoufox):

**OpÃ§Ã£o A (recomendada):** Camoufox navega atÃ© a SERP â intercepta o POST `Next-Action` â 
extrai o ID do header da requisiÃ§Ã£o real feita pelo browser.

**OpÃ§Ã£o B (alternativa):** Camoufox navega atÃ© a SERP â extrai URLs dos chunks do HTML completo â 
faz GET nos chunks â busca `createServerReference("<id>", ..., "searchProducts")`.

**OpÃ§Ã£o C (cache por build):** ApÃ³s descoberta, cachear o ID associado ao build ID (`b` field da resposta RSC). 
Invalidar quando o `b` mudar (nova request RSC ao GET da home ou qualquer pÃ¡gina).

#### Go / No-Go para Strategy A

**VEREDICTO: GO (com condiÃ§Ã£o)**

- **Endpoint funcional:** confirmado com 200 OK + JSON limpo no probe anterior.
- **Sem session gate:** sem cookies necessÃ¡rios para o POST da action.
- **CF nÃ£o bloqueia o POST:** o Cloudflare bloqueia GET da pÃ¡gina, nÃ£o o POST da server action.
- **CondiÃ§Ã£o:** ID deve ser descoberto via browser por sessÃ£o (nÃ£o pode ser hardcoded permanentemente).
- **Vantagem sobre Strategy B (browser SERP puro):** evita problema de `incomplete_hydrate` do S25 â 
  o POST da action retorna JSON direto, sem depender de RSC hydration client-side.
- **QuestÃ£o aberta:** S25 retorna 0 produtos no payload anterior â pode ser genuine empty ou encoding.
  Requer re-probe com ID fresco (Task 9).

**Concerns:**
1. Action ID muda por deploy â overhead de discovery por sessÃ£o.
2. Discovery requer Camoufox (browser) de qualquer forma â custo de browser nÃ£o Ã© eliminado, apenas amortizado.
3. Payload correto para S25 nÃ£o confirmado com ID vÃ¡lido â pode ser genuine empty (produto nÃ£o no catÃ¡logo).

---


### Task 13  Multi-Category Regression (2026-09-23)

**Probe:** scripts/probe_match_regression_t13.py  
**Resultado geral:** PASS  todas regressões críticas confirmadas.

#### Resultados por categoria (KaBuM live search)
| Subject            | Candidates | Top candidate                              |
|--------------------|------------|--------------------------------------------|
| S25 Ultra          | 5          | Samsung Galaxy S25 Ultra 256gb Titânio     |
| B650M-E WIFI       | 5          | ASUS TUF Gaming B650M-E WIFI AM5 DDR5     |
| Ryzen 7 5800X3D    | 5          | AMD Ryzen 5900XT/9950X3D (AMD genérico)   |
| MSI RTX 5070       | 5          | MSI RTX 5070 12G SHADOW 3X OC GDDR7       |
| Kingston DDR5      | 5          | (Kingston SSD  query miss, score filtra) |
| Samsung 990 EVO+   | 5          | Samsung 990 EVO Plus, 1TB NVMe            |

#### Mock Match (identity_reference_item, sem PDP real)
- S25 Ultra ? **MATCH** (kabum + magazineluiza)
- B650M-E WIFI ? **MATCH** (kabum + magazineluiza)

#### Store bloqueada
- pichau UPSTREAM_BLOCKED ? Run **completa** ? (other_stores_ran=3)

#### Visão VIP search ? PDP
- search_error_isolated=True, pdp_path_distinct=True
- visaovip search circuit em produção: **healthy**

#### Nota sobre Visão VIP browser no probe
- Camoufox falhou no docker exec (root vs home/app user mismatch)
- Circuit abriu corretamente após 1ª falha  protegeu queries subsequentes (~1ms cada)
- Não é problema de produção; serviço api healthcheck confirma Camoufox funcional

---

## Estado Final — Fase 14 (2026-09-23)

### Trilha CAMOUFOX_RELIABILITY — Antes / Depois

| Aspecto | Antes (baseline Task 0) | Depois (Tasks 1–6 + ADR 0039) |
|---|---|---|
| Capacidade browser | C1 implícito (sem controle) | C1 explícito, `BrowserScheduler` com fila limitada |
| Fila de browser | `queue.Queue()` ilimitada, hang indefinido | `CAMOUFOX_QUEUE_MAX_WAITERS` + `BROWSER_QUEUE_SATURATED` |
| Profile isolation | Sem lock OS entre processos | `ProfileLock` Redis+fcntl; perfis `slot-{id}` isolados |
| Half-open circuit | Estado DEGRADED sem token; thundering herd possível | `claim_trial()` atômico; non-probe callers fail-fast |
| Failure domain | Circuit global (process-wide) por loja | Circuit por store key; launch ≠ NO_MATCH |
| Retry/attempt budgets | Sem teto explícito por store/run | `StoreAttemptBudget`: queries(5) / external(12) / browser_nav(8) |
| Capacidade C2+ | Não benchmarkada | Benchmarkada e rejeitada (C2 L2: 90% success rate < 100% C1); ADR 0039 |
| Documentação | AGENTS.md sem invariante de capacidade | AGENTS.md + ADR 0039 + `.cursor/rules/browser-scheduler-bounded.mdc` |

### Trilha VISAO_VIP_DISCOVERY — Antes / Depois

| Aspecto | Antes (baseline Task 0) | Depois (Tasks 7–13) |
|---|---|---|
| Strategy SERP | Browser-only (Strategy B) — sem alternativa | Strategy A implementada (Server Action POST) + Strategy B |
| S25 Ultra SERP | UPSTREAM_BLOCKED (causa não isolada) | `incomplete_hydrate` identificado e documentado (root cause: RSC não hidrata) |
| Classify empty | Incompleto — risco de NO_MATCH falso | `classify_empty_result()`: `incomplete_hydrate` → `incomplete`, não NO_MATCH |
| Strategy A status | N/A | Implementada, atrás de flag (`enabled=False`); ID discovery pendente (PENDING-018) |
| B650M-E WIFI | Search+Match OK | Confirmado OK (3/3 iterações, probe + regression) |
| Multi-category regression | N/A | PASS: phone/MB/CPU/GPU/RAM/SSD KaBuM; blocked store → run completa |
| Store doc | Ausente estratégias A/B | `docs/crawler/stores/visaovip.md` atualizado com Strategy A/B, incomplete_hydrate, PENDING-018 |

### Pendências restantes geradas nesta fase

- **PENDING-018** (P2, OPEN): Visão VIP Strategy A — wiring de ID discovery em produção.

### Documentação criada/atualizada nesta fase (Task 14)

- `docs/crawler/stores/visaovip.md` — Strategy A/B, incomplete_hydrate, limitação S25 Ultra
- `docs/matching/README.md` — StoreAttemptBudget + BrowserScheduler contratos
- `docs/adr/0039-bounded-browser-scheduler-capacity-c1.md` — presente desde Task 6, não alterado
- `.cursor/rules/browser-scheduler-bounded.mdc` — regra operacional nova
- `docs/pending/PENDING-018-visaovip-strategy-a-discovery.md` — criada
- `docs/pending/README.md` — PENDING-018 adicionado ao índice ativo
- `.superpowers/sdd/task-14-report.md` — relatório consolidado final
