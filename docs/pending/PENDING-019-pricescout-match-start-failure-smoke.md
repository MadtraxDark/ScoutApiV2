# PENDING-019 — Completar smoke de falhas no start do Product Match

- Status: OPEN
- Tipo: TESTING
- Prioridade: P2
- Área: frontend/product-match
- Origem: 2026-09-23 — investigação da confirmação entre PriceScout e ScoutApiV2
- Atualizado: 2026-09-23

## Contexto

O fluxo normal foi validado ao vivo: o clique recebeu `202 Accepted`, a Run foi
persistida e reclamada pelo `match-runner`, e o polling recuperou a Run após
reload. A correção também valida a confirmação de Run no frontend e evita
cliques concorrentes no hook. Ainda falta executar a matriz de falhas de UI
solicitada para indisponibilidade, erro/timeout e interrupção durante a busca.

## Feito

- Smoke real com API + `match-runner`: POST 202, polling 200 e Run `running`
  com attempt 1, lease válida e atividade recente.
- Reload recupera a Run ativa e mantém o timer.
- `tests/unit/test_match_runs.py`: 21 testes passaram, incluindo start
  duplicado idempotente e semântica de Run ativa.
- `PriceScout/utils/match-run.test.ts`: 9 testes passaram, incluindo rejeição
  de resposta terminal, ausente ou de outro produto.
- Typecheck e ESLint direcionado do frontend passaram.

## Falta

- Exercitar visualmente API indisponível, resposta HTTP de erro e início lento;
  verificar erro visível, ausência de timer antes da confirmação e desbloqueio
  do botão.
- Disparar cliques repetidos no frontend e comprovar um único POST.
- Interromper worker/API durante uma Run de teste controlada e verificar a
  recuperação/saída do estado ativo pela lease.

## Por que não terminou

A validação ao vivo criou uma Run real que permanece em background. Não foi
seguro derrubar API ou worker durante essa execução. A janela de navegador
Playwright isolada abriu sem sessão; o teste autenticado foi feito no Chrome
do operador. Os casos restantes precisam de uma Run descartável em ambiente
controlado ou de interceptação de rede no navegador autenticado.

## Impacto

O fluxo normal está confirmado. Os caminhos de falha estão cobertos pela
captura de erros existente e pelas proteções de código, mas ainda sem smoke
visual por cenário.

## Relacionado

- `PriceScout/hooks/useProductMatchRun.ts`
- `PriceScout/utils/match-run.test.ts`
- `tests/unit/test_match_runs.py`
- `docs/adr/0036-persistent-product-match-runs.md`

## Pronto quando

Cada cenário de falha acima tiver teste automatizado ou smoke reproduzível,
com evidência de erro visível, timer consistente, deduplicação e recuperação
do estado após interrupção.
