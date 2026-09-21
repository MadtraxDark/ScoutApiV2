# PENDING-014 — Extrair timers de promo em spiders live (Pichau/ML/Shopee)

- Status: OPEN
- Tipo: INCOMPLETE
- Prioridade: P2
- Área: crawler/promotions + monitoring
- Origem: 2026-09-21 — monitoramento persistente ADR 0030
- Atualizado: 2026-09-21

## Contexto

O scheduler persistente (ADR 0030) e o contrato `metadata.promotion`
estão prontos. Falta ligar extractors ao scrape live das lojas onde o
timer existe mas o spider ainda não emite expiry estruturado — e
aprofundar Pichau além do HTML SSR.

## Feito

- ADR 0030 + `docs/monitoring.md` + `docs/crawler/promotions.md`
- Schema `store_listings` monitoring/promo + migration `0025`
- Worker DB-driven + lease + OfferRefresh hooks
- Extractor Terabyte validado no HTML live (`ctd41251` →
  `2026/09/28 10:00:59` America/Sao_Paulo)
- Heurísticas ML/Shopee + `metadata.promotion` reader
- Frontend PriceScout last/next check + countdown absoluto

## Falta

- Spider TerabyteShop / Pichau (ainda `implemented=False`) para coleta
  periódica real dessas lojas
- Pichau: investigação browser/XHR/hydration do timer (SSR sem countdown)
- Shopee spider: emitir `metadata.promotion` quando `flash_sale`/`end_time`
  estiver no payload da selected model
- Mercado Livre spider: emitir `finish_date`/expiry quando presente no PDP
  ou fonte pública estruturada (sem seller token)

## Por que não terminou

Escopo do core de scheduling entregue; wiring por spider e deep-dive
Pichau browser ficaram como follow-up para não bloquear o relógio
persistente.

## Investigação

### O que foi testado

- Terabyte PDP via curl_cffi: countdown jQuery absoluto OK
- Pichau PDP via curl_cffi: ~420KB SSR sem `__NEXT_DATA__`, sem
  `countdown`/`expires`/`special_to_date`; só JSON-LD preço

### Fontes consultadas

- ML Seller Promotions docs (`finish_date` LIGHTNING)
- Mageplaza Magento countdown GraphQL (contexto Pichau/Magento — não
  confirmado na loja)

### Condição para continuar

- Implementar spiders Terabyte/Pichau **ou** capturar XHR autenticado
  do operador na Pichau headed
- PDP Shopee/ML com flash sale ativa para fixture + parser

## Impacto

Listings dessas lojas monitoram preço a cada 12h, mas não antecipam
check por promo expiry até o spider emitir timestamp confiável.

## Done when

- [ ] Pichau: fonte estruturada de expiry documentada ou “sem timer”
      confirmado via browser
- [ ] Shopee live flash_sale → `metadata.promotion.expires_at`
- [ ] ML PDP/deal → `metadata.promotion.expires_at` quando disponível
- [ ] Terabyte spider (quando implementado) reutiliza
      `extract_terabyte_countdown`
