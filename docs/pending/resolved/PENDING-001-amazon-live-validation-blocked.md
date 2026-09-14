# PENDING-001 — Validação live Amazon `/crawl/offer` (Camoufox ainda bloqueado)

- Status: RESOLVED
- Tipo: TESTING
- Prioridade: P1
- Área: crawler/amazon
- Resolvido: 2026-09-12

## Resolução

Caminho de produção = **HTTP-first** (ADR 0016). Validado live:

- US `B09V9Z1WLN` via `OfferScrapeService` (~3s, sem browser/proxy)
- BR com Buy Box via HTTP (ver PENDING-002 / fixtures `br_live_buybox_*`)

Fallback Camoufox/proxy após challenge HTTP permanece frágil (robot-check) e
foi documentado como **limitação aceita** em `docs/crawler/stores/amazon.md`
— sem CAPTCHA bypass.
