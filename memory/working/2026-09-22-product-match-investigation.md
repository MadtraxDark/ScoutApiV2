# Working log — Product Match investigation

Date: 2026-09-22
Objective: Investigar e corrigir fluxo completo "Buscar preços em outras lojas" (ScoutApiV2 + PriceScout), regressão S25 Ultra 256GB.

## Checklist

- [x] Arquitetura real vs ADR 0036 confirmada (MatchRun + polling, sem SSE)
- [x] Reprodução frontend/API do caso S25 Ultra
- [x] Classificação de falhas por etapa
- [x] Correções de causa raiz (sem hardcode)
- [x] Testes unitários relevantes
- [x] Live S25 Ultra (run `4b74fc43-…`)
- [x] Docs/memory atualizados
- [ ] E2E frontend completo (PriceScout UI) — validar manualmente no browser do operador
- [ ] Multi-category live (GPU/monitor) — não bloqueante desta sessão; regressão unitária smartphone OK

## Ground truth

- Produto: `800a4caa-c179-4760-a2cf-7edaf75253c2`
- Amazon BR ASIN: `B0DSYJCY45` (encontrado live após correção de cor)
- Nissei: MATCH com variante 256 GB black (storage na PDP/variante)

## Steps / evidence

### Sintoma

Runs `failed` com `INTERNAL_ERROR` (statement_timeout no UPDATE de `product_match_runs`) e `UPSTREAM_REQUEST_ERROR` (scrape da referência Shopping China). Polling FE com 429.

### Causas raiz

1. Worker mantinha lock de row na sessão longa durante o Match → `on_store_outcome` timeout.
2. `select_reference_url` empatava scores e podia escolher Shopping China.
3. Falha de scrape da referência abortava a Run inteira (sem fallback de identidade).
4. Dual worker (API + match-runner) ambos enabled.
5. Matcher: `titanio preto != titanio` tratado como CONFLICT (deveria ser MISSING).

### Correções

- `match_run_worker.py`: commit antes do Match; outcomes em sessão curta; fallback identidade; swallow erro de outcome.
- `match_run_service.py`: prioridade de loja na referência; `_as_utc` em finalize.
- `compose.yaml` / `.env.example`: API worker off por padrão.
- `identity.py`: `_colors_compatible` para finish vs hue.
- PriceScout: backoff em 429 no polling.

### Live validation `4b74fc43-9e80-46fb-8b41-21ae25eab6f8`

- status: completed; 9 stores; 6 MATCH; 3 NO_MATCH; 0 ERROR; ~773s
- amazon_br → MATCH `B0DSYJCY45`
- amazon_us → MATCH `B0DP3GQ4QY`
- nissei → MATCH 256 GB black
- notification: 1× PRODUCT_MATCH_COMPLETED

## Decisions

- ML/Shopee: permanecem `match_enabled=false` (PENDING-017)
- Não hardcode ASIN/SKU

## Pendências restantes

- PENDING-016 / PENDING-017 (já existentes)
- E2E UI PriceScout (operador)
- Multi-category live opcional

## Timings

- Live S25 Ultra após fix: ~12,9 min (772920 ms) para 9 lojas
- Antes: falha em ~1 min (lock) ou ~3 min (UPSTREAM referência)
