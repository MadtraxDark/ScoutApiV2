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
   `match_run_max_attempts`, marcar `failed` com `failure_code=worker_lost`
   (não bloquear o produto eternamente).
7. Notificação terminal idempotente por `(match_run_id, type)`.
8. **Active (API/UX) ≠ `status` sozinho:** uma Run só é efetivamente ativa se
   `pending` **ou** (`running` **e** lease válida / `claim_expires_at > now`).
   `GET …/active` com lease expirada responde **204** (não finge worker vivo).
9. **Política C (híbrida):** worker reclaim da mesma Run (skip de
   `MatchStoreRun` já `match|no_match|error`); `POST start` com Run stale
   terminaliza `worker_lost` e cria nova; sweeper terminaliza exhausted.
10. Timer UX usa `active_since` (`claimed_at` da attempt atual, senão
    `started_at`) — downtime offline **não** conta como processamento.
11. Heartbeat só no worker (`MATCH_RUN_HEARTBEAT_INTERVAL_SECONDS`); fencing
    por `worker_id` + `attempts` em heartbeat / store outcome / finalize.

## Justificativa

Product Match dura minutos e deve sobreviver à navegação. O padrão de fila
durável já existe no projeto (monitor/imagens). Polling moderado é mais simples
e robusto que manter stream aberto; SSE/WebSocket não resolvem ownership
persistente da operação.

## Consequências positivas

- UI deixa de ser dona do lifecycle.
- Reload preserva elapsed e bloqueio de nova busca **enquanto a lease for válida**.
- Restart da API/worker recupera jobs (reclaim) ou libera produto (`worker_lost`).
- Crash / power-loss não deixa banner eterno: active exige lease válida.
- Logs/notificações auditáveis no site.
- Código SSE morto removido do fluxo.

## Trade-offs / consequências negativas

- Feedback de progresso por loja deixa de ser streaming contínuo; o banner
  mostra elapsed (+ opcionalmente stores_completed/stores_total).
- Latência de detecção de conclusão ≈ intervalo de polling (poucos segundos).
- Após lease expirar, há janela em que `GET active` é 204 até reclaim ou
  `POST start` / sweeper terminalizar — intencional (não fingir worker vivo).
- Crescimento de linhas de log por Run — retenção agressiva fica para fase
  futura (documentada).

## Configuração (Settings)

| Env | Default | Papel |
|---|---|---|
| `MATCH_RUN_LEASE_SECONDS` | 600 | TTL da lease |
| `MATCH_RUN_HEARTBEAT_INTERVAL_SECONDS` | 120 | Renovação (só worker) |
| `MATCH_RUN_RECOVERY_INTERVAL_SECONDS` | 30 | Cadência de reconcile |
| `MATCH_RUN_MAX_ATTEMPTS` | 3 | Após N claims → `worker_lost` |
| `MATCH_RUN_SWEEP_INTERVAL_SECONDS` | 2 | Poll do claim loop |
| `MATCH_STORE_WALL_TIMEOUT_SECONDS` | 180 | Deadline absoluto por loja (`0`=off); ERROR `STORE_WALL_TIMEOUT` |
| `MATCH_RUN_WALL_TIMEOUT_SECONDS` | 2700 | Deadline da run desde claim (`0`=off); FAILED `RUN_WALL_TIMEOUT` |
| `MATCH_RUN_WATCHDOG_STALE_SECONDS` | 600 | Sem progresso real → `os._exit(78)` (`0`=off) |
| `MATCH_RUN_WATCHDOG_ENABLED` | true | Liga/desliga watchdog de processo |
| `MATCH_RUN_WATCHDOG_CHECK_INTERVAL_SECONDS` | 5 | Intervalo do daemon watchdog |

### Emenda 2026-09-23 — Hang watchdog (híbrido)

Lease resolve **worker desapareceu**. Watchdog resolve **worker vivo sem progresso**.
Store/run wall resolvem budgets cooperativos. Heartbeat de lease **não** conta como
progresso. Exit code `78` (`MATCH_WORKER_HANG_EXIT_CODE`); Compose
`restart: unless-stopped` + reclaim ADR 0036. Detalhes: `docs/matching/README.md`.

## Endpoints

| Método | Path | Papel |
|---|---|---|
| POST | `/products/{id}/match-runs` | Start (202); stale → `worker_lost` + nova |
| GET | `/products/{id}/match-runs/active` | Efetivamente ativa ou 204 |
| GET | `/match-runs/{id}` | Status (poll); inclui `active_since` / `attempts` |
| GET | `/products/{id}/match-runs` | Histórico |
| GET | `/match-runs/{id}/details` | Relatório |
| GET/POST | `/notifications*` | Central persistente |

`POST /match` síncrono permanece para usos não-UI / tooling.
