# Task 4 Report — Phase 4: Cross-process profile ownership

**Status:** ✅ COMPLETO  
**Data:** 2026-09-23

---

## Decision Gate — PROFILE_LOCK_PROOF

Prova executada DENTRO do container `scoutapiv2-api-1` na pasta
`/home/app/.cache/scout-api/camoufox-profiles/slot-0` (bind mount real
`./data/camoufox-profiles` do Docker Desktop Windows).

| Fase | Backend | Resultado |
|------|---------|-----------|
| 1 — File lock exclusivity | fcntl.flock | **PASS** — challenger bloqueou 1.0s enquanto A segurava |
| 2 — File lock crash recovery | fcntl.flock | **PASS** — B adquiriu em 0.002s após kill -9 A |
| 3 — Redis SET NX exclusivity | Redis SET NX PX | **PASS** — challenger não conseguiu enquanto A segurava |
| 4 — Redis TTL crash recovery | Redis TTL=3s | **PASS** — B adquiriu em 2.73s após kill -9 A |

**Conclusão:** ambos os backends funcionam no bind mount real. File lock (fcntl) tem
recuperação de crash instantânea (~2ms), mas não protege *cross-container* com
certeza em todos os ambientes Docker Desktop. Redis é a escolha primária: prova
idêntica de exclusividade e recuperação dentro do TTL.

**Lock escolhido: `CAMOUFOX_PROFILE_LOCK=redis` (primary)**  
File lock documentado como alternativa testada, disponível via `mode=file`.

---

## Implementação

### Arquivos criados/modificados

| Arquivo | Alteração |
|---------|-----------|
| `scripts/probe_profile_lock_multiprocess.py` | **Novo** — probe de 4 fases (exclusivity + crash recovery para file e Redis) |
| `src/scout_api/modules/crawler/core/profile_lock.py` | **Novo** — `ProfileLock` Protocol + `NullProfileLock` + `RedisProfileLock` + `FileProfileLock` + `build_profile_lock()` |
| `src/scout_api/modules/crawler/core/browser_slot.py` | `BrowserSlotLease` recebe campo `_profile_lock_lease: ProfileLockLease | None` |
| `src/scout_api/modules/crawler/core/browser_scheduler.py` | `acquire()` chama `_wrap_with_profile_lock()` após liberar `self._lock`; `release()` libera o profile lock antes de devolver o slot ao pool; novos params `profile_lock`, `profile_base_path`, `profile_lock_timeout_ms` |
| `src/scout_api/core/config.py` | `camoufox_profile_lock`, `camoufox_profile_lock_ttl_ms`, `camoufox_profile_lock_timeout_ms` |
| `.env.example` | Documentação das 3 novas variáveis |
| `tests/unit/test_profile_lock.py` | **Novo** — 20 testes TDD cobrindo todos os backends e integração com o scheduler |

### Decisão de design crítica — fora do lock

`_wrap_with_profile_lock()` é chamado FORA do `with self._lock:` do scheduler:

```
com self._lock → obter slot_id → sair do lock → adquirir profile lock
```

Motivo: `threading.Lock` não é reentrante. O caminho de rollback em
`_wrap_with_profile_lock` re-adquire `self._lock` para devolver o slot ao pool
quando o profile lock dá timeout. Chamar dentro do lock causaria deadlock.

### Configurações (Settings)

```
CAMOUFOX_PROFILE_LOCK=redis        # redis | file | off
CAMOUFOX_PROFILE_LOCK_TTL_MS=600000  # 10min TTL de segurança no Redis
CAMOUFOX_PROFILE_LOCK_TIMEOUT_MS=30000  # max espera por profile lock
```

### Rollback de emergência

```
CAMOUFOX_PROFILE_LOCK=off
```
Emite WARN em cada acquire; nunca bloqueia o crawler.

---

## Testes

```
tests/unit/test_profile_lock.py — 20/20 PASS (1.73s)
tests/unit/test_browser_scheduler.py — 7/7 PASS (0.57s)
```

Cobertura dos testes:
- NullProfileLock: acquire/release sem erros, WARN emitido
- RedisProfileLock: exclusividade, B adquire após A liberar, TTL crash recovery,
  compare-and-delete (token errado não libera), fail-open sem Redis
- FileProfileLock: exclusividade por threading, timeout correto, graceful no Windows
- BrowserScheduler: lease contém profile_lock_lease, lock liberado no release,
  timeout de profile lock devolve slot ao pool
- build_profile_lock: todos os modos + fallbacks

---

## Prova no bind mount real (Docker)

```
Prova run em: scoutapiv2-api-1
Volume: ./data/camoufox-profiles → /home/app/.cache/scout-api/camoufox-profiles
Proto: /home/app/.cache/scout-api/camoufox-profiles/slot-0/.profile.lock

Phase 1: File PASS (exclusive=True, elapsed=1.0s bloqueado)
Phase 2: File PASS (fast_recovery=True, elapsed_after_kill=0.002s)
Phase 3: Redis PASS (exclusive=True, elapsed=1.0s bloqueado)
Phase 4: Redis PASS (ttl_crash_recovery_ok=True, elapsed=2.73s para TTL=3s)
```

---

## Concerns / Observações

1. **File lock cross-container**: a prova foi feita dentro de um único container
   (multiprocessing/fork). Locks `fcntl.flock` entre CONTÊINERES DIFERENTES no
   mesmo bind mount não foram provados nesta tarefa. Redis cobre esse cenário de
   forma garantida.

2. **TTL sem renovação (Phase 4 default)**: o TTL padrão é 10 min. Sessões
   camoufox com muitos fetches (warm_max_fetches=40) podem exceder esse tempo.
   Renovação de lease não foi implementada nesta fase. Risco: baixo no C1
   (capacity=1, sessões recicladas antes de 10 min típico).

3. **Wire no CamoufoxHtmlFetcher**: concluído (fix pós-relatório).

---

## Wiring produção (fix crítico)

| Arquivo | Alteração |
|---------|-----------|
| `html_fetcher.py` | `_build_browser_scheduler()` + `camoufox_profiles_root()`; `build_html_fetcher` passa `build_profile_lock` → `BrowserScheduler` (`profile_lock`, `profile_base_path`, `profile_lock_timeout_ms`) |
| `product_scrape_service.py` | `get_shared_html_fetcher()` → `build_redis_gateway` + settings `camoufox_profile_lock*` |

`CAMOUFOX_PROFILE_LOCK=off` → `NullProfileLock`; default `redis` via Settings.

```
uv run python -m pytest tests/unit/test_profile_lock.py tests/unit/test_browser_scheduler.py -v
→ 25 passed, 2 skipped (2.16s)
```

---

## Pendências restantes

- Integration test cross-container (api + monitor na mesma pasta de profiles)

Fora disso: nenhuma pendência desta tarefa em aberto.
