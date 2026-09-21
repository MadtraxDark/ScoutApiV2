# Monitoramento persistente de ofertas

Canônico: este documento + [ADR 0030](adr/0030-persistent-offer-monitoring.md).

## Princípio

**O relógio pertence ao PostgreSQL, não ao processo.**

Cada `store_listings` monitorado carrega:

| Campo | Papel |
|---|---|
| `last_checked_at` | Última tentativa/verificação observada |
| `last_successful_check_at` | Último scrape comercial OK |
| `next_check_at` | Próxima elegibilidade (scheduler) |
| `next_regular_check_at` | Cadência 12h sem distorcer por retry |
| `check_*` | Lease do worker (`SKIP LOCKED` / claim) |
| `promotion_*` | Estado **atual** da promoção temporizada |

Histórico de preço/promo: `offer_snapshots` + `offer_events` (append-only).
Expirar promoção **não** apaga Product/Listing/histórico.

## Cadência

- Config: `OFFER_REFRESH_INTERVAL_HOURS` (default **12**).
- Após sucesso: `next_regular_check_at = now + 12h + jitter`.
- `next_check_at = min(regular, promotion_expires_at + grace)` quando há
  promo ativa com expiry confiável.
- Semântica: **sliding** a partir do último sucesso (não grade absoluta
  fixa). Documentado no ADR.

## Catch-up / downtime

Se a API/worker ficar offline e `next_check_at` passar:

1. No próximo sweep, o listing está due.
2. Executa **uma** verificação atual.
3. Registra `last_check_scheduled_for` + `last_check_delay_seconds`.
4. **Não** recria N snapshots das janelas perdidas.

## Retry transitório

Falhas (`UPSTREAM_BLOCKED`, timeout, etc.):

- `consecutive_failures++`
- `next_check_at = now + backoff` (`OFFER_MONITOR_RETRY_BASE_SECONDS` …
  `OFFER_MONITOR_RETRY_MAX_SECONDS`)
- `next_regular_check_at` **não** avança só por falha.

Erro técnico **nunca** vira `out_of_stock`.

## Concurrency

Worker claim:

1. Seleciona due (`monitoring_enabled`, `status=active`,
   `next_check_at <= now` **ou** promo ativa já expirada).
2. PostgreSQL: `FOR UPDATE SKIP LOCKED`.
3. Grava lease (`check_worker_id`, `check_claim_expires_at`).
4. Se o worker morrer, o lease expira e outro worker recupera.

Scrape paralelo da mesma URL continua coberto pelo single-flight Redis
(ADR 0020).

## Processo

```text
PostgreSQL (next_check_at)
    → monitor worker (sweep)
    → claim + lease
    → OfferRefreshService
    → snapshot/eventos + agenda
```

Comando:

```bash
python -m scout_api.modules.monitoring.worker
# ou
python -m scout_api.modules.monitoring.worker --once
```

Compose: serviço `monitor` (mesmo image da API).

API HTTP **não** carrega a durabilidade no lifespan.

## Observabilidade

- Logs: `offer_monitor_check` com delay/duration/status/next_check.
- Admin: `GET /monitor/diagnostics`, `POST /monitor/sweep`
  (`require_admin`).
- Heartbeat: tabela `monitor_scheduler_state`.

## Frontend (PriceScout)

- Exibe `last_checked_at` / `next_check_at` a partir da API.
- Countdown de promo = `promotion_expires_at - now` (absoluto).
- Ao zerar localmente: refetch; autoridade continua no backend
  (`promotion_commercially_active`).

## Promoções por loja

Ver [crawler/promotions.md](crawler/promotions.md).
