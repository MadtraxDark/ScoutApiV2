# ADR 0032: Product Match HTTP-first + Camoufox warm reuse

- Status: Accepted
- Data: 2026-09-21

## Contexto

O Product Match cross-store estava funcional, porém frequentemente levava
dezenas de minutos. O profiling mostrou que o custo dominante era o ciclo de
vida do Camoufox: **launch → navigate → close** por URL (SERP e PDP), sob
`threading.Lock` global no `CamoufoxHtmlFetcher`, com lojas processadas em
série. Já existiam early-stop por `auto_match`, prefilter de título SERP e
cap de SERPs vazias — insuficientes enquanto cada fetch pagava cold start.

Pesquisa (Playwright docs, Camoufox issues/docs, Scrapfly, Scraping Central,
padrões HTTP-first OSS): reutilizar o **processo/browser** e escalar
HTTP → browser só com evidência é a alavanca correta; pool grande ou 20
browsers simultâneos aumenta bloqueio/custo.

## Problema / decisão necessária

Como reduzir drasticamente o tempo total do Product Match **sem** reduzir
cobertura, baixar thresholds, transformar ERROR em NO_MATCH ou tornar
Camoufox o caminho padrão?

## Alternativas consideradas

- **A — Timeout artificial / skip de lojas lentas:** rejeitada (esconde
  falha; quebra cobertura).
- **B — Baixar `max_candidates` / thresholds:** rejeitada (precisão).
- **C — Pool de N browsers Camoufox em paralelo:** adiada; risco de WAF,
  `.parentlock` de perfil e memória; Camoufox já serializa por lock.
- **D — Warm reuse do persistent context + HTTP-first por loja + caches
  request-scoped no Match:** adotada.
- **E — Concorrência ampla entre lojas agora:** adiada com pendência; GTIN
  mid-flight e lock Camoufox limitam o ganho até warm reuse estabilizar.

## Decisão

1. **Camoufox warm reuse (default on):** manter um persistent context vivo
   por fetcher (`direct` / `proxied`), chaveado por locale+profile+proxy;
   nova **page** por URL; reciclar após `CAMOUFOX_WARM_MAX_FETCHES` ou
   mudança de fingerprint; AliExpress continua **oneshot** (perfil temp).
2. **HTTP-first expandido:**
   - Amazon SERP aceita HTML com `s-search-result` sem browser (ADR 0016).
   - KaBuM SERP/PDP via urllib quando `__NEXT_DATA__` (ou sinais PDP) estão
     presentes; challenge → Camoufox.
   - Shopping China `/quick_search` e Mercado Livre curl_cffi permanecem.
3. **Product Match request-scoped:**
   - `include_images=False` forçado;
   - cache de SERP `(store, query)` e de PDP por URL canônica;
   - dedupe de queries normalizadas;
   - early-stop / title reject / empty-search cap preservados.
4. **Camoufox permanece fallback** após evidência insuficiente ou bloqueio
   classificado (Proxy Cost Mode inalterado).

## Justificativa

Launch de browser (~segundos + settle + possível warmup) × N candidatos × N
queries × N lojas explica dezenas de minutos. Warm reuse + HTTP-first atacam
a causa sem enfraquecer o matcher. Caches request-scoped evitam refetch da
mesma evidência dentro de um único `/match`.

## Consequências positivas

- Menos `browser_launch`; métricas `browser_reused` / contadores no fetcher.
- SERP Amazon/KaBuM podem completar em HTTP quando a loja entrega HTML útil.
- Match não baixa galeria nem refetcha a mesma PDP no mesmo run.

## Trade-offs / consequências negativas

- Sessão warm mantém processo Firefox residente (memória); recycle por
  `WARM_MAX_FETCHES` mitiga.
- Locale sticky na sessão: troca de locale/proxy força relaunch.
- KaBuM/Amazon HTTP podem degradar se o HTML público mudar → fallback
  browser obrigatório (não vira NO_MATCH).

## Emenda (2026-09-21) — waves + `MATCH_STORE_CONCURRENCY`

A alternativa **E** (concorrência entre lojas) foi **adotada de forma
restrita**, sem invalidar D:

1. **Wave 1 (serial):** lojas com `gtin_exposure_rank <= 55` (KaBuM, Best Buy,
   Nissei, Shopping China, Amazon BR/US) — preserva aprendizado de GTIN
   mid-flight antes do restante.
2. **Wave 2 (paralela):** demais lojas via `ThreadPoolExecutor` com
   `MATCH_STORE_CONCURRENCY` (default 3). Camoufox roda em **owner thread**
   dedicada (`_PlaywrightOwnerLoop`) — Playwright sync é thread-affine;
   o lock sozinho não basta quando wave-2 chama `fetch` de workers.
3. Challenge settle **fail-fast** após um `try_resolve` falho (evita hang de
   minutos em Magalu/Akamai durante `/match`).
4. Warm session **não** é descartada em todo `RequestError` (ex.:
   `UPSTREAM_BLOCKED` de challenge); só quando o contexto Playwright está
   envenenado (Sync API / greenlet / target closed).
5. Ordenação Match agrupa **locale affinity** e waves em três fases:
   GTIN+locale dominante (serial) → resto da mesma locale (paralelo) →
   outras locales (serial). Playwright Sync **não** tolera múltiplos
   contextos Camoufox vivos na mesma owner-thread (pool multi-session
   descartado após `Sync API inside the asyncio loop`).

Pool de N browsers Camoufox **em paralelo** (**C**) permanece rejeitado.
