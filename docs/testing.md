# Testes — ScoutApiV2

Como rodar a suíte sem inflar o ciclo de desenvolvimento.

## Categorias

| Categoria | Onde | Rede real? | Browser? | Objetivo |
|---|---|---|---|---|
| **Unit** | `tests/unit/` | Não | Não | Parsers, identity, scoring, fakes |
| **Integration** | `tests/integration/` + `@pytest.mark.integration` | Serviços locais (Redis/Postgres) | Não | Repositórios, coordenação |
| **Live** | `@pytest.mark.live` ou scripts `scripts/_live_*` | Sim (lojas) | Só se necessário | Validar fixture vs site real |
| **Slow / E2E** | `@pytest.mark.slow` / `e2e` | Depende | Depende | Fluxos caros, cross-store |

## Comandos

```bash
make test              # padrão diário: unit + integration; exclui live/slow
make test-unit         # só tests/unit
make test-integration  # -m integration
make test-live         # -m live (rede real)
make test-full         # tudo
make test-performance  # suite rápida + --durations=25 + resumo budget-aware

python -m pytest --durations=50   # profiling
```

Equivalente direto:

```bash
python -m pytest -m "not live and not slow"
```

Observabilidade de tempo (budgets, `slow_operation`, retries, browser):
[`performance.md`](performance.md).
## Regras para novos testes

1. **Parser / identity / match scoring** → fixture HTML/JSON local em `tests/fixtures/`, unit test.
2. **Não** inicialize Camoufox para assertar parsing de fixture.
3. **Não** use `time.sleep` real para TTL/backoff em unit — avance o relógio (`monkeypatch` em `time.monotonic`) ou delays zero.
4. Cross-store live (“ache X em todas as lojas”) → `live`/`slow` ou script em `scripts/`, **não** no `make test`.
5. Preferir `include_images=False` salvo teste específico de galeria.
6. Product Match em produção já faz: early-stop após `auto_match`, pré-filtro barato por título SERP, cap de SERP vazia. Não reimplemente loops N×queries×candidates em scripts de validação (evite pré-probe + match duplicado).

## Budgets (após profiling 2026-09-20)

| Suite | Meta |
|---|---|
| Unit (`tests/unit`) | < 20s |
| `make test` (sem live/slow) | < 60s |
| Live / cross-store | separado; reportar `match_store_timing` nos logs |

O gargalo histórico de ~10 min **não** era a suíte unitária (~9s): vinha de scripts live cross-store (SERP + scrape serial por loja, às vezes com pré-probe duplicado).

## pytest-xdist

Avaliável para unit isolados (`pytest -n auto`). **Não** adotar por padrão em live (rate limit / browser compartilhado). Confirmar isolamento de DB/porta antes de ligar no CI.

## CI

Não há workflow GitHub Actions versionado neste repositório no momento. Se/quando existir: cache de pip/uv, separar job `test` (determinístico) de `test-live`, não baixar browser em jobs unit.

## Markers (`pyproject.toml`)

- `integration`
- `live`
- `slow`
- `e2e`
