# ADR 0010: Estratégia Camoufox contra Cloudflare / WAF

- Status: Accepted
- Data: 2026-09-10

## Contexto

Nissei (Cloudflare) e Magazine Luiza (Akamai) bloqueiam coleta. O ADR 0009
adotou Camoufox; na prática ainda há três falhas distintas: desafio JS
(“Just a moment…” / “Un momento…”), hard-block de IP (“Attention Required”),
e detecção em Docker.

## Problema / decisão necessária

Quais mitigações operar no `CamoufoxHtmlFetcher` sem espalhar lógica anti-bot
pelos spiders?

## Alternativas consideradas

- Só aumentar settle/timeout
- Só proxy residencial
- Camoufox + perfil persistente + warm-up + geoip + virtual display
- Solvers externos de Turnstile / scraping APIs

## Decisão

Endurecer o fetcher Camoufox com:

1. `headless="virtual"` no Linux (Xvfb) + `geoip=True` + `os=windows` + `humanize`
2. `persistent_context` + `user_data_dir` para reutilizar `cf_clearance`
3. Warm-up da origem (ex.: `https://nissei.com/py/`) antes do produto
4. `wait_until=domcontentloaded` + tentativa de `networkidle`
5. `disable_coop` para iframes Turnstile (com `i_know_what_im_doing`)
6. Distinguir hard-block (não retryável; pedir `CAMOUFOX_PROXY_URL`) de desafio JS
7. Lock em torno do fetch (perfil Firefox não é concurrent-safe)

## Justificativa

Validado em probe com IP limpo: virtual+geoip resolve o desafio; perfil +
warm-up estabiliza cookies. Hard-block de IP não é solucionável por fingerprint —
proxy residencial continua necessário nesse caso (docs Camoufox geoip/proxy).

## Consequências positivas

- Menos `UPSTREAM_BLOCKED` em desafios transitórios
- Mensagem clara quando o IP está banido
- Cookies WAF sobrevivem a restarts via volume Docker

## Trade-offs / consequências negativas

- Fetch mais lento (warm-up + settle)
- Perfil em disco e volume Compose extras
- `disable_coop` pode ser detectável em WAFs sofisticados
- Hard-block ainda exige IP/proxy limpo
- ``ScrapeGuard`` (cooldown por URL/domínio + cache) reduz rajadas que
  provocam banimento de IP; ver settings ``SCRAPE_*``

