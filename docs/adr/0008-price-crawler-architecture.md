# ADR 0008: Arquitetura modular do crawler de preços

- Status: aceito
- Data: 2026-09-10

## Contexto

O projeto precisa coletar ofertas de múltiplas regiões sem acoplar regras de negócio
à FastAPI, nem sobrecarregar lojas ou perder histórico.

## Decisão

Adicionar `modules/crawler` com `BaseStoreSpider`, modelo normalizado, parsing monetário
por moeda, TTL adaptativo, fila de prioridade, cache e seams para Redis/proxy/persistência.
Os primeiros adapters são Kabum (BRL), Best Buy (USD) e Nissei (PYG). O spider falha
explicitamente em parsing essencial ausente; não emite preço zero.

## Consequências

Novas lojas implementam somente identidade, URLs e parsing específico. O backend local
permite testes rápidos; uma implantação distribuída deve substituir os stores locais
por Redis/PostgreSQL e adicionar repositórios de histórico idempotentes.
