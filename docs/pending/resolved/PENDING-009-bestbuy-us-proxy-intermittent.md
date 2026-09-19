# PENDING-009 — Best Buy scrape intermitente com proxy US (RESOLVED)

- Status: RESOLVED
- Tipo: BUG
- Prioridade: P1
- Área: crawler/bestbuy
- Origem: 2026-09-19 — benchmark PS5 + correção Akamai `NET_RESET`
- Resolvido: 2026-09-19

## Resolução

### Causa raiz

Akamai Bot Manager em `bestbuy.com` combina (1) reputação/geo de IP,
(2) TLS/browser fingerprint, (3) sensor JS `bmak` que emite `_abck`/`bm_sz`,
(4) binding cookie↔IP. Navegação **fria** direto no PDP com egress inconsistente
gera `NS_ERROR_NET_RESET` (TCP RST **antes** de HTML de CAPTCHA) — por isso
solvers de imagem/CAPTCHA não ajudam nesse sintoma.

### Pesquisa (2026-09-19)

| Fonte | Achado |
|---|---|
| Playwright #16749 / SO | `NET_RESET` = RST de rede/WAF, não bug local do browser |
| Camoufox #555 / #450 | Builds FF135 detectados pela Akamai; master em FF152+ OK; `disableInstantAnimations` mitiga patch de animações |
| ProxyHat / Aethyn / HProxy | Warm homepage → mint `_abck` → sticky residential IP; HTTP frio falha |
| Scraperly / Scrapeless | Vendors pagos / curl_cffi TLS; priorizamos Camoufox já no projeto |
| GitHub sensor helpers (`web-re-toolkit`, `akamai-v3-*`) | Forge offline de `sensor_data` frágil e supply-chain; **descartado** — sensor real no Camoufox (ADR 0017) |
| DataImpulse docs | `__cr.us` + `;sessid.*` sticky ~30 min |

### Implementado

- Homepage warmup Best Buy + settle longo + mouse nudge (`bmak`)
- Sticky `sessid.scoutbb` + `__cr.us` + `geoip=True` + locale `en-US`
- Referer origin no PDP; retry in-session após `NET_RESET`; retry StoreAware
- `disableInstantAnimations` no launch Camoufox
- Camoufox no Docker já em **152.0.4-beta.30** (além do vetor FF135)

### Validação live

- PDP Slim Digital: após `NET_RESET` + retry → preço `699.00`
- Segunda PDP 825GB: sucesso em ~9s → preço `599.99`
- Sem fabricar oferta a partir de bloqueio

### Não adotado

- Serviços pagos de “Akamai bypass API” (Scrapeless etc.) sem autorização
- Bibliotecas de forge de `sensor_data` / reverse de payload Akamai
- Sempre-on proxy (viola Proxy Cost Mode)

## Relacionado

- `docs/crawler/stores/bestbuy.md`
- `src/scout_api/modules/crawler/services/html_fetcher.py`
- ADR 0014, ADR 0017
