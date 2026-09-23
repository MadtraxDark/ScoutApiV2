# Task 10 Report — Strategy B fallback + error taxonomy

## O que foi feito

### 1. Taxonomia de erros (novos códigos preferidos)
- `UPSTREAM_WAF_BLOCKED` — SERP bloqueada por WAF/challenge (era `UPSTREAM_BLOCKED`)
- `SEARCH_INCOMPLETE_RESPONSE` — SERP chegou mas sem resultados parseáveis (era `UPSTREAM_BLOCKED`)
- Ambos adicionados a `PROXY_FALLBACK_ERROR_CODES` (alias on-read; legado `UPSTREAM_BLOCKED` preservado)
- `product_match_service.py`: novos códigos causam `break` no loop de queries (igual a `SEARCH_UNSUPPORTED`)

### 2. Cadeia A→B em `StoreSearchService.search()`
- Detecta adapter com `try_strategy_a` (duck-type, compatível com VisaoVipSearchAdapter)
- A SUCCESS → ranking + dedup por product_id → retorna; B não é chamado
- A NO_RESULTS → lista vazia genuína; B não é chamado
- A UNAVAILABLE/BLOCKED/INVALID_RESPONSE/ERROR → fallback para B (browser SERP)
- Flag desabilitada ou `action_id` vazio → vai direto para B
- Budget preservado: 1 query A + 1 fetch B = 1 slot externo se A falhar

### 3. Config
- `visaovip_search_action_id: str = ""` adicionado ao `AppSettings` (deploy-coupled; vazio desabilita A)

### 4. Dedup por product_id
- Função `_dedup_candidates_by_product_id()` pública em `store_search_service.py`
- Usada nos resultados da Strategy A antes de retornar

### 5. UI path
- `MatchStoreError.message` vem de `str(exc)` — mensagens em português, sem snake_case exposto

### 6. Testes
- `tests/unit/test_visaovip_search_chain.py` — 13 testes novos (todos PASSED)
- `tests/unit/test_store_search_service.py` — 2 testes atualizados para novos códigos
- 96 testes relevantes PASSED; 808 testes totais da suíte unit PASSED (2 skipped pre-existentes)

## Arquivos alterados
- `src/scout_api/core/config.py`
- `src/scout_api/modules/crawler/core/exceptions.py`
- `src/scout_api/modules/matching/store_search_service.py`
- `src/scout_api/modules/matching/product_match_service.py`
- `tests/unit/test_store_search_service.py`
- `tests/unit/test_visaovip_search_chain.py` (novo)

## Pendências restantes
Nenhuma. Todos os critérios de done da Task 10 foram atendidos.
