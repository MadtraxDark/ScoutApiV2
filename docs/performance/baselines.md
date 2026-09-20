# Performance baselines — ScoutApiV2

Resumo histórico leve (sem APM). Atualize após profiling relevante
(`make test-performance`, live cross-store, Docker build).

Fonte de budgets: [`../performance.md`](../performance.md).

| Workflow | Baseline | Current | Delta | Medido em | Notas |
|---|---:|---:|---:|---|---|
| Unit tests (`tests/unit`) | ~9–12s | ~6s (c/ integration rápida) | — | 2026-09-20 | `make test-performance` → 483 passed / 6.0s |
| `make test` (sem live/slow) | &lt; 60s | 6.0s | ok | 2026-09-20 | outlier: `test_health_is_public` ~2.7s (cold import) |
| Cross-store live Product Match | ~10m (histórico) | otimizado c/ early-stop | — | 2026-09-20 | ver logs `match_timing_summary` |
| Docker build | — | — | — | — | preencher no próximo build |

Como medir:

```bash
make test-performance
# Live / cross-store: inspecionar match_timing_summary e slow_operation nos logs
```

Regressão significativa (ex. +2× ou salto de dezenas de segundos em unit) deve
aparecer no relatório final da tarefa mesmo com testes verdes.
