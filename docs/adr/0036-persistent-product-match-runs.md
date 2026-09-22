# ADR 0036: Product Match como job persistente + polling (sem SSE)

- Status: Accepted
- Data: 2026-09-22
- Relacionado: [ADR 0019](0019-product-matching.md), [ADR 0030](0030-persistent-offer-monitoring.md), [ADR 0031](0031-durable-image-optimization-queue.md)

## Contexto

O fluxo PriceScout "Buscar preços em outras lojas" usava `POST /match/stream`
(SSE): o frontend mantinha uma conexão HTTP aberta enquanto o Product Match
rodava (minutos). Sair da página, recarregar ou abortar o `fetch` cancelava a
experiência de progresso; o lifecycle da busca ficava acoplado à página React.

## Problema / decisão necessária

Como executar Product Match de forma que:

1. o request inicial responda rápido;
2. a busca sobreviva a navegação/reload/fechamento da aba;
3. exista no máximo uma Run ativa por produto;
4. haja recovery após restart do processo;
5. o frontend consulte status sem SSE/WebSocket;
6. notificações e logs fiquem consultáveis depois?

## Alternativas consideradas

### A) Manter SSE (`StreamingResponse` / EventSource)

- Progresso em tempo quase real.
- Conexão aberta por minutos; proxies/timeouts; abort do cliente interrompe a UX;
  busca "pertence" à página; difícil reabrir progresso após reload.

### B) WebSocket

- Bidirecional e com reconnect.
- Infra e complexidade desproporcionais para um job por produto; ainda acopla
  presença do cliente ao feedback; não resolve ownership da operação no backend.

### C) Persistent Job + Polling (escolhida)

- `POST` cria `ProductMatchRun` (status `pending`) e responde **202 Accepted**.
- Worker PostgreSQL (lease + `FOR UPDATE SKIP LOCKED`, padrão ADR 0030/0031)
  executa o mesmo `ProductMatchService`.
- Frontend faz polling leve de status; timer de elapsed usa `started_at`
  persistido; toast efêmero (`react-hot-toast`); central de notificações
  persistente; relatório estruturado por loja.

## Decisão

1. Remover `POST /match/stream` e todo o contrato SSE desse fluxo (sem
   compatibilidade paralela).
2. Entidade `product_match_runs` + `match_store_runs` + `match_candidate_logs`
   + `user_notifications`.
3. Índice único parcial: no máximo uma Run com status `pending|running` por
   `product_id`.
4. HTTP **202** no start (operação assíncrona aceita) com corpo contendo `id` e
   status; start duplicado devolve a Run ativa com `already_active=true`
   (idempotente, sem segunda execução).
5. Polling: `GET /match-runs/{id}` (payload compacto) e
   `GET /products/{id}/match-runs/active` — rate scope `poll` (bucket
   separado do CRUD/crawler; ver `docs/security/api-auth.md`).
6. Lease/heartbeat + reclaim de Runs `running` com lease expirado; após
   `match_run_max_attempts`, marcar `failed` (não bloquear o produto
   eternamente).
7. Notificação terminal idempotente por `(match_run_id, type)`.

## Justificativa

Product Match dura minutos e deve sobreviver à navegação. O padrão de fila
durável já existe no projeto (monitor/imagens). Polling moderado é mais simples
e robusto que manter stream aberto; SSE/WebSocket não resolvem ownership
persistente da operação.

## Consequências positivas

- UI deixa de ser dona do lifecycle.
- Reload preserva elapsed e bloqueio de nova busca.
- Restart da API/worker recupera jobs.
- Logs/notificações auditáveis no site.
- Código SSE morto removido do fluxo.

## Trade-offs / consequências negativas

- Feedback de progresso por loja deixa de ser streaming contínuo; o banner
  mostra elapsed (+ opcionalmente stores_completed/stores_total).
- Latência de detecção de conclusão ≈ intervalo de polling (poucos segundos).
- Crescimento de linhas de log por Run — retenção agressiva fica para fase
  futura (documentada).

## Endpoints

| Método | Path | Papel |
|---|---|---|
| POST | `/products/{id}/match-runs` | Start (202) |
| GET | `/products/{id}/match-runs/active` | Active ou 204 |
| GET | `/match-runs/{id}` | Status (poll) |
| GET | `/products/{id}/match-runs` | Histórico |
| GET | `/match-runs/{id}/details` | Relatório |
| GET/POST | `/notifications*` | Central persistente |

`POST /match` síncrono permanece para usos não-UI / tooling.
