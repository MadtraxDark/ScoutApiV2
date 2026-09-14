# PENDING-002 — Acesso live Amazon BR instável (HTTP 500 / Buy Box vazia)

- Status: RESOLVED
- Tipo: TESTING
- Prioridade: P1
- Área: crawler/amazon
- Resolvido: 2026-09-12

## Resolução

- PDPs BR em estoque com Buy Box capturados via HTTP-first:
  fixtures `B0GY5SB1P3`, `B0GN4S2ZSK`; pipeline live também
  `B0GN515WT6`, `B0H2CXMFLX`
- Fixtures sanitizadas: `tests/fixtures/amazon/br_live_buybox_1.html`,
  `br_live_buybox_2.html`
- Testes: `test_amazon_br_live_captured_buybox_fixtures`
- Soft retry HTTP (~1.25s) quando PDP sem Buy Box / sem OOS claro
- Referer same-marketplace no `UrllibHtmlFetcher`
- Intermitência residual de widgets Buy Box e HTTP 500 em SKUs inválidos
  documentados em `docs/crawler/stores/amazon.md` (known limitations)
