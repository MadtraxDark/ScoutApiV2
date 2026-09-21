# ADR-0030: Monitoramento persistente de ofertas (PostgreSQL-driven)

- Status: Accepted
- Data: 2026-09-21

## Contexto

O ScoutApiV2 já persiste histórico comercial em `offer_snapshots` /
`offer_events` e expõe `POST /offers/refresh`. Faltava um **relógio
durável** para revalidar listings a cada 12 horas e reagir a promoções
com expiração explícita — sem depender do uptime do processo FastAPI.

Infra atual: PostgreSQL (SoT), Redis (cache/single-flight de scrape),
sem Celery/RQ (ADR 0020 rejeitou broker só para scrape cache).

## Problema / decisão necessária

Como agendar rechecagens periódicas e expiração de promoções de forma
que:

1. o prazo sobreviva a restart/offline da API;
2. checks vencidos sejam processados no retorno (sem inventar histórico);
3. duas instâncias não crawlem o mesmo listing em paralelo;
4. promoções que expiram antes de 12h antecipem o próximo check;
5. o estado comercial continue no domínio (`store_listings`), não só na
   tabela interna de uma lib de scheduler.

## Alternativas consideradas

### A — Timers em memória / `asyncio.sleep(12h)` / FastAPI BackgroundTasks

Rejeitada: perde prazo no restart; não escala; viola o princípio
“tempo é estado persistente”.

### B — APScheduler + SQLAlchemyJobStore

Persiste jobs, mas:

- FAQ oficial: **não compartilhe job store entre processos** (risco de
  duplicate/miss);
- misfire/coalesce pode reexecutar janelas perdidas de forma opaca;
- o estado comercial (`last_checked_at`, `promotion_expires_at`) ainda
  precisaria viver no domínio.

Fontes: [APScheduler user guide](https://apscheduler.readthedocs.io/en/latest/userguide.html),
[FAQ job store sharing](https://apscheduler.readthedocs.io/en/latest/faq.html),
[SO: missed jobs on restart](https://stackoverflow.com/questions/78009942/apscheduler-missed-jobs-not-run-when-process-is-restarted).

### C — Celery + Celery Beat (+ Redis)

Poderoso, mas adiciona broker/worker stack. ADR 0020 já evita Celery
para scrape. Beat persistente não substitui `next_check_at` no domínio.
Só justificável com carga/ops que ainda não temos.

### D — Redis-backed delayed queues

Redis não é SoT no ScoutApiV2. Atraso/expiroução de promoção não pode
depender de cache LRU.

### E — PostgreSQL-driven sweep + `FOR UPDATE SKIP LOCKED` / lease

Listing carrega `next_check_at` / lease. Worker separado faz sweep
frequente, claim atômico, chama `OfferRefreshService`. Catch-up =
`WHERE next_check_at <= now()`. Um único refresh após downtime
(coalesce implícito). Padrão amplamente usado (PgQueuer, pgwerk,
PostForge, etc.).

Fontes: [PgQueuer](https://github.com/janbjorge/pgqueuer),
[pgwerk](https://pypi.org/project/pgwerk/),
[PostForge](https://pypi.org/project/postgresforge/),
discussões SKIP LOCKED job queue.

### F — Cron externo só dispara sweep

Aceitável como *gatilho*, desde que o cron **não** seja a fonte do
prazo por oferta. Compatível com E.

## Decisão

Adotar **E**: monitoramento **DB-driven** sobre `store_listings`.

- Unidade = `StoreListing` (oferta por loja), não Product.
- Intervalo padrão: `OFFER_REFRESH_INTERVAL_HOURS=12` (após sucesso:
  `next_check_at = now + 12h + jitter`).
- Promo ativa com `expires_at` anterior: `next_check_at = min(regular, expires_at + grace)`.
- Worker dedicado (`python -m scout_api.modules.monitoring.worker`),
  processo separado da API.
- Claim: lease (`check_worker_id`, `check_claim_expires_at`) +
  `SKIP LOCKED` no PostgreSQL (optimistic claim no SQLite de teste).
- Downtime: ao voltar, processa vencidos **uma vez**; registra
  `delay_seconds`; não recria snapshots das janelas perdidas.
- Falha transitória: `retry_at` via backoff (`offer_monitor_retry_*`),
  sem avançar a cadência regular.
- Promoção expirada: `promotion_status=expired`, deixa de ser vigente;
  histórico em `offer_events` / snapshots; listing/product preservados.
- Refresh manual bem-sucedido recalcula `next_check_at` (evita
  re-crawl imediato do scheduler).

## Justificativa

Alinha com PostgreSQL já existente, evita Celery sem necessidade,
mantém o relógio no domínio comercial, recupera naturalmente após
offline e coordena multi-worker com primitiva nativa do Postgres.

## Consequências positivas

- Prazo e promo sobrevivem restart.
- Observabilidade clara (`/monitor/diagnostics`, heartbeat).
- Reuso de `OfferRefreshService` / `offer_diff` / scrape single-flight.
- Frontend countdown baseado em `promotion_expires_at` absoluto.

## Trade-offs / consequências negativas

- Sweep periódico (latência até `OFFER_MONITOR_SWEEP_INTERVAL_SECONDS`).
- Snapshot a cada check bem-sucedido (inclui unchanged) — aceitável na
  cadência de 12h; política mais agressiva de dedupe fica para depois.
- Spiders ainda não implementados (Terabyte/Pichau) limitam extração
  live até existirem fetchers; extractors/HTML helpers já estão prontos.
