# Task 6 Report — Phase 6: Capacity Decision + ADR

**Data:** 2026-09-23  
**Decisão:** C1 (capacity=1) — produção inalterada.

## Executado

1. **ADR 0039 criado** (`docs/adr/0039-bounded-browser-scheduler-capacity-c1.md`): documenta `BrowserScheduler` + `ProfileLock` + `claim_trial` + decisão C1; ADR 0032 (pool N browsers rejeitado) permanece Accepted e não supersedido.
2. **`docs/adr/README.md` atualizado** — ADR 0039 adicionado ao índice.
3. **`AGENTS.md`** — invariante "Concorrência de browser limitada (crítico)" adicionado: capacity=1 validado, proíbe aumento sem benchmark de produção, cita ADR 0032 e 0039.
4. **Working log corrigido** (`memory/working/2026-09-23-camoufox-visaovip-reliability.md`) — recomendação C2 de Task 5 marcada como supersedida; adjudicação C1 registrada com motivos.
5. **`CAMOUFOX_BROWSER_CAPACITY=1`** no `.env.example` — confirmado; não alterado.

## Motivos da decisão C1

- C2 L2 (Visão VIP, anti-bot): 1 erro / 10 fetches = 90% < 100% de C1 → viola `success ≈ C1`.
- P95 C2/C3 não melhorou ≥15% em nenhuma camada; throughput não compensa reliability.
- Bench incompleto (sem `BrowserScheduler` de produção, sem terceira loja, sem carga compose).

## Pendências restantes

Nenhuma nesta task. Reabertura de C2+ documentada no ADR 0039 (condições: success_rate ≥ 100% em loja real anti-bot N≥20, P95 não piora ≥15%, harness de produção).
