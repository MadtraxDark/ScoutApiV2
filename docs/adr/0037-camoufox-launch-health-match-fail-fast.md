# ADR-0037: Camoufox launch health + Product Match fail-fast de infraestrutura

- Status: Accepted
- Data: 2026-09-23

## Contexto

Product Match runs atingiam ~30+ minutos quando o Camoufox falhava ao
iniciar: o entrypoint fazia `chown -R` no bind mount Windows
(`./data/camoufox-profiles`), gerando milhares de `Input/output error` e
perfil/cache inconsistente; o Playwright usava timeout de launch padrão
(180 s); falhas eram classificadas como `UPSTREAM_REQUEST_ERROR`; o Match
continuava queries/lojas; a owner-thread serializava cada tentativa.

## Problema / decisão necessária

Como manter o bind mount de perfis (seed headed compartilhado) sem
corromper o FS no Windows, separar timeout de launch vs navegação, e
impedir que falha estrutural de browser vire `NO_MATCH` ou some N×180 s?

## Alternativas consideradas

- `privileged: true` / desligar sandbox global sem evidência — rejeitado
  (risco + mascara a causa).
- Remover bind mount e usar named volume só — rejeitado (quebra seed
  headed local documentado em ADR 0010).
- Timeout global de 30 min no MatchRun como “fix” — rejeitado (esconde
  a causa e ainda desperdiça wall-time).
- Tratar launch failure como `UPSTREAM_BLOCKED` com proxy fallback —
  rejeitado (proxy não corrige binary/perfil/EIO).

## Decisão

1. **Entrypoint:** não fazer `chown -R` no árbol de perfis. Só `mkdir -p`;
   opcional `CAMOUFOX_CHOWN_PROFILES=root-only` (não-recursivo) para named
   volume Linux. Em startup, purgar caches descartáveis
   (`cache2` / `startupCache` / `thumbnails` / locks) quando
   `CAMOUFOX_PURGE_DISPOSABLE_CACHE=true` (default), preservando
   cookies/prefs/logins.
2. **`CAMOUFOX_LAUNCH_TIMEOUT_MS`** (default 45 s) separado de
   `CAMOUFOX_TIMEOUT_MS` (navegação). Passado como `timeout=` no launch
   Camoufox/Playwright.
3. **Classificação:** falha estrutural de launch →
   `BROWSER_LAUNCH_ERROR` / `BROWSER_INFRASTRUCTURE_UNAVAILABLE`. Timeout
   de `Page.goto` permanece erro de navegação.
4. **Circuit breaker de processo** (`browser_health.BrowserCircuitBreaker`):
   abre só em falha estrutural de launch; TTL + half-open; compartilhado
   entre fetchers direct/proxied.
5. **Product Match:** em código de infra browser, `break` da loja (não
   `continue` em N queries); outcome `error` com esse código — **nunca**
   `NO_MATCH`. Stores HTTP-first seguem sem Camoufox quando o circuit
   está aberto (falham só ao precisar de browser).
6. **Reference identity-first:** se `CanonicalProduct` tem title, o
   worker usa `match_from_item(identity_reference_item(...))` antes de
   scrape live da URL de referência.

## Justificativa

Corrige a causa raiz (FS + timeout + classificação + loop do Match) sem
abrir a superfície de segurança do container nem abandonar o seed de
perfil headed. ERROR≠NO_MATCH preserva telemetria e UI corretas.

## Consequências positivas

- Boot sem flood de chown/EIO no Docker Desktop Windows.
- Launch falha em segundos (budget), não 180 s × N.
- Match termina com mix MATCH/NO_MATCH/ERROR sem wall-time de dezenas
  de minutos por browser quebrado.
- HTTP-first (ADR 0032) permanece intacto.

## Trade-offs / consequências negativas

- Bind mount Windows ainda não aplica ownership Linux (documentado;
  `root-only` só para named volumes).
- Purge de `cache2` no boot pode aumentar o primeiro launch (frio) após
  restart — aceitável vs hang.
- Circuit aberto pode falhar stores browser-only por até
  `BROWSER_CIRCUIT_COOLDOWN_SECONDS` mesmo se o problema era transitório;
  half-open mitiga.
