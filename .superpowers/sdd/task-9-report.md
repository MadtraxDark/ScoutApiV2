# Task 9 Report — Strategy A (searchProducts Server Action)

**Data:** 2026-09-23

---

## Status

**CONCLUÍDO** — Strategy A implementada com TDD. 31/31 testes passando. Lint e mypy limpos.

---

## Implementação

### Arquivos criados / modificados

| Arquivo | Ação |
|---|---|
| `src/scout_api/modules/matching/search_adapters/paraguay/visaovip_action_strategy.py` | **Criado** — módulo Strategy A |
| `src/scout_api/modules/matching/search_adapters/paraguay/visaovip.py` | **Modificado** — adicionado `try_strategy_a()` |
| `src/scout_api/core/config.py` | **Modificado** — flag `visaovip_search_action_enabled` |
| `tests/unit/test_visaovip_strategies.py` | **Criado** — 31 testes TDD |

### StrategyResult enum

```python
class StrategyResult(StrEnum):
    SUCCESS = "success"
    NO_RESULTS = "no_results"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"
    INVALID_RESPONSE = "invalid_response"
    ERROR = "error"
```

### Contrato de descoberta do action ID

- `discover_action_id_from_chunk_js(chunk_text)` — extrai ID de chunk JS
  - Regex suporta forma direta **e** Turbopack: `createServerReference\)?\(...)`
  - Validado contra `chunk_serp3.body` capturado na Task 8
- `discover_action_id_from_serp_html(html, ...)` — scan de página hidratada
  - Requer HTML completo (≥ 10 KB); CF shell → retorna None
  - Produção: usar intercepção via Playwright (`page.on("request")`)

### Parsing RSC

`parse_rsc_response(body, slug) → (StrategyResult, candidates | None, build_id | None)`

| Caso | StrategyResult |
|---|---|
| `products: [...]` com itens | SUCCESS |
| `products: []` válido | NO_RESULTS |
| `1:E{"digest":"..."}` | BLOCKED |
| JSON sem chave `products` | INVALID_RESPONSE |
| Corpo vazio | UNAVAILABLE |
| JSON inválido | INVALID_RESPONSE |

### HTTP POST

`call_search_products(slug, action_id, *, timeout)` → faz POST e retorna `(StrategyResult, candidates)`

- 404 → UNAVAILABLE (ID rotacionou)
- 500/outros → BLOCKED
- Exception de rede → ERROR

### Adapter

`VisaoVipSearchAdapter.try_strategy_a(query, *, action_id, enabled, timeout)`:
- `enabled=False` → UNAVAILABLE sem HTTP (feature flag)
- Delega para `call_search_products` com slug gerado pelo `_search_term_slug`
- Path original (`build_search_request` / `parse_candidates`) **inalterado**

### Flag de config

```env
VISAOVIP_SEARCH_ACTION_ENABLED=false  # default — aguarda smoke live
```

---

## Testes

| Suite | Resultado |
|---|---|
| `test_visaovip_strategies.py` (31 testes) | ✅ 31 passed |
| `tests/unit/` completo (817 testes) | ✅ 817 passed, 2 skipped |
| ruff check | ✅ limpo |
| mypy | ✅ limpo |

---

## Smoke live (Docker)

Docker não disponível nesta sessão. Live smoke de B650M + S25 requer Docker +
Camoufox para descoberta do action ID atual (deploy-coupled). Procedure:

```bash
docker compose run --rm --no-deps api \
  python scripts/probe_visaovip_search_action.py
```

O script da Task 8 já cobre discovery + POST validation. Para habilitar:

```env
VISAOVIP_SEARCH_ACTION_ENABLED=true
```

---

## Pendências restantes

- Live smoke B650M + S25 com Docker/Camoufox: **PENDENTE** (sem Docker disponível)
- Task 10: cadeia de fallback Browser SERP → Strategy A → Strategy B (ainda não implementada)
- Flag `VISAOVIP_SEARCH_ACTION_ENABLED` permanece `false` até smoke live confirmar green
