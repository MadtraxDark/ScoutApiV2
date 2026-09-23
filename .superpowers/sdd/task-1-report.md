# Task 1 Report — BrowserScheduler C1 Hardening

**Data:** 2026-09-23  
**Status:** ✅ COMPLETO

---

## 1. Arquivos criados / modificados

| Ação | Arquivo |
|---|---|
| Criado | `src/scout_api/modules/crawler/core/failure_domains.py` |
| Criado | `src/scout_api/modules/crawler/core/browser_slot.py` |
| Criado | `src/scout_api/modules/crawler/core/browser_scheduler.py` |
| Modificado | `src/scout_api/core/config.py` — 4 novas settings |
| Modificado | `.env.example` — documentação das 4 novas settings |
| Modificado | `src/scout_api/modules/crawler/services/html_fetcher.py` — params `scheduler`/`scheduler_enabled` em `CamoufoxHtmlFetcher`, novo `_fetch_via_owner`, wiring em `build_html_fetcher` |
| Modificado | `src/scout_api/modules/crawler/services/product_scrape_service.py` — passa settings de scheduler para `build_html_fetcher` |
| Criado | `tests/unit/test_browser_scheduler.py` — 6 testes TDD |

---

## 2. Evidência TDD RED → GREEN

### RED (antes da implementação):
```
$ uv run pytest tests/unit/test_browser_scheduler.py -v
ERROR tests/unit/test_browser_scheduler.py
ModuleNotFoundError: No module named 'scout_api.modules.crawler.core.browser_scheduler'
```

### GREEN (após implementação):
```
$ uv run pytest tests/unit/test_browser_scheduler.py -v
tests/unit/test_browser_scheduler.py::test_capacity_one_second_job_waits_or_queues PASSED
tests/unit/test_browser_scheduler.py::test_queue_saturated_fails_fast PASSED
tests/unit/test_browser_scheduler.py::test_cancel_while_queued_does_not_get_slot PASSED
tests/unit/test_browser_scheduler.py::test_fifo_order PASSED
tests/unit/test_browser_scheduler.py::test_snapshot_reflects_state PASSED
tests/unit/test_browser_scheduler.py::test_slot_id_assigned PASSED
6 passed in 0.50s
```

### Suíte completa de unit tests (sem os 3 pré-existentes com bug de módulo):
```
714 passed, 4 warnings in 36.22s
```
Nenhuma regressão introduzida.

---

## 3. Lint e tipagem

```
ruff check → All checks passed!
mypy src/…/failure_domains.py src/…/browser_slot.py src/…/browser_scheduler.py
         src/…/config.py → Success: no issues found in 4 source files
```

---

## 4. Decisões de design

### BrowserScheduler (FIFO / bounded queue)
- `deque[_Waiter]` garante FIFO determinístico
- `_Waiter.slot_id` é definido sob lock ANTES de `event.set()` → leitura thread-safe sem lock adicional
- Race condition timeout vs. pre-grant: tratada com `except ValueError` no handler de timeout, sem loop infinito
- Poll interval: 50 ms (cancel_event detection latency aceitável)
- `_wake_next_unlocked` sinaliza exatamente 1 waiter por release (FIFO)

### Isolamento direct vs. proxied
- Cada `CamoufoxHtmlFetcher` recebe seu próprio `BrowserScheduler` → direto não bloqueia proxied e vice-versa

### Feature flag `CAMOUFOX_BROWSER_SCHEDULER_ENABLED`
- `true` por padrão → scheduler ativo
- `false` → legacy path (sem scheduler; `_fetch_via_owner` direto)
- Rollback imediato via env sem redeploy

### Navegação/Camoufox INALTERADOS
- `_fetch_locked`, `_launch_kwargs`, seletores, waits, humanize → sem alteração
- Só acquire/release adicionados em volta do `_owner.call()`

---

## 5. Novos settings (config.py + .env.example)

```
CAMOUFOX_BROWSER_SCHEDULER_ENABLED=true  # Feature flag rollback
CAMOUFOX_BROWSER_CAPACITY=1              # Não aumentar sem benchmark C1→C2→C3
CAMOUFOX_BROWSER_QUEUE_CAPACITY=32       # Max waiters; excesso → BROWSER_QUEUE_SATURATED
CAMOUFOX_QUEUE_TIMEOUT_MS=60000          # ms aguardando slot → BROWSER_QUEUE_TIMEOUT
```

---

## 6. Métricas emitidas

- `browser_slot_acquired_immediate` / `_from_queue` / `_race` — debug
- `browser_slot_released` — debug com `poison`, `active`, `queue_depth`
- `browser_queue_saturated` — warning com depth/capacity/active
- `snapshot()` retorna: `depth`, `capacity`, `active`, `waits`, `queue_capacity`, `queue_timeout_ms`, `queue_timeout_count`, `total_acquisitions`

---

## 7. Sem commits

Nenhum commit realizado conforme instrução da tarefa.

---

## 8. Pendências restantes

Nenhuma pendência nova introduzida por esta tarefa.

As 3 falhas de coleta pré-existentes em `test_distributed_cooldown.py`, `test_distributed_single_flight.py`, `test_redis_cache.py` (ModuleNotFoundError: `tests`) são anteriores a esta tarefa e não relacionadas.

---

## 9. Performance

- 6 novos testes: 0.50 s total (nenhum acima do budget WARN de 500 ms/unit)
- Suíte de 714 testes: 36.22 s (sem regressão observada)
- O overhead do scheduler (acquire/release) é desprezível em C1: bloqueio apenas quando slot ocupado, sem polling com proxy ativo

---

## 10. Fix Notes — Review Task 1 (2026-09-23)

Aplicados todos os findings críticos e importantes levantados na revisão do Task 1.

### CRITICAL 1 + IMPORTANT 6 — failure_domain=browser_infrastructure

Todas as 3 saídas de erro de fila agora usam `log_failure(FailureDomain.BROWSER_INFRASTRUCTURE, ...)`:

| Código              | Evento de log             |
|---------------------|---------------------------|
| BROWSER_QUEUE_SATURATED | `browser_queue_saturated` |
| BROWSER_QUEUE_TIMEOUT   | `browser_queue_timeout`   |
| BROWSER_JOB_CANCELLED   | `browser_job_cancelled`   |

Arquivo: `src/scout_api/modules/crawler/core/browser_scheduler.py`

### CRITICAL 2 — product_scrape_service.py pass-through

Verificado: `get_shared_html_fetcher()` já passava os 4 settings obrigatórios
(`camoufox_browser_scheduler_enabled`, `camoufox_browser_capacity`,
`camoufox_browser_queue_capacity`, `camoufox_queue_timeout_ms`) desde o Task 1.
Import verificado OK: `python -c "from scout_api.modules.crawler.services.product_scrape_service import ProductScrapeService; print('OK')"`.

### IMPORTANT 3 — browser_queue_wait_ms + canonical names

- `_Waiter` ganhou campo `enqueue_time: float = 0.0` (preenchido em `time.monotonic()` no enqueue).
- `browser_queue_wait_ms` emitido nos eventos: `browser_slot_acquired_from_queue`, `browser_slot_acquired_race`, `browser_queue_timeout`, `browser_job_cancelled`.
- `snapshot()` agora inclui chaves canônicas: `browser_queue_depth`, `browser_queue_capacity`, `browser_active_jobs`, `browser_capacity`, `browser_queue_timeout_count` (em adição às chaves legadas).

### IMPORTANT 4 — Teste para BROWSER_QUEUE_TIMEOUT

Adicionado `test_queue_timeout()` em `tests/unit/test_browser_scheduler.py`:
- `queue_timeout_ms=120`, 1 slot ocupado, worker entra na fila e expira.
- Assertivas: código `BROWSER_QUEUE_TIMEOUT`, `browser_queue_timeout_count == 1`, chave legada `queue_timeout_count == 1`.

### IMPORTANT 5 — cancel_event em CamoufoxHtmlFetcher.fetch()

Adicionado parâmetro keyword-only `cancel_event: threading.Event | None = None` em
`CamoufoxHtmlFetcher.fetch()`. Valor é passado diretamente para `self._scheduler.acquire(cancel_event=cancel_event)`.
Compatível com chamadas existentes (default `None`). Não quebra o `HtmlFetcher` Protocol.

### Evidência de testes

```
$ uv run pytest tests/unit/test_browser_scheduler.py -v
tests/unit/test_browser_scheduler.py::test_capacity_one_second_job_waits_or_queues PASSED
tests/unit/test_browser_scheduler.py::test_queue_saturated_fails_fast PASSED
tests/unit/test_browser_scheduler.py::test_cancel_while_queued_does_not_get_slot PASSED
tests/unit/test_browser_scheduler.py::test_fifo_order PASSED
tests/unit/test_browser_scheduler.py::test_snapshot_reflects_state PASSED
tests/unit/test_browser_scheduler.py::test_slot_id_assigned PASSED
tests/unit/test_browser_scheduler.py::test_queue_timeout PASSED
7 passed in 0.61s — nenhum acima do WARN unit (500ms)
```
