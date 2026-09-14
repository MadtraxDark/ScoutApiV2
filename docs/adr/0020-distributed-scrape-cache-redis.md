# ADR 0020: Cache e coordenação distribuída de scrape via Redis

- Status: Accepted
- Data: 2026-09-14

## Contexto

O ScoutApiV2 já possui `ScrapeGuard` com cache de resultados, single-flight e
cooldown por URL/domínio — tudo **local ao processo**. O Compose já inclui
Redis (`REDIS_URL`), mas a aplicação não o utilizava. Em deploy com várias
réplicas da API, cada instância podia:

- repetir live scrape da mesma PDP;
- disparar stampede contra o mesmo marketplace;
- consumir Camoufox / proxy residencial / exposição WAF desnecessariamente;
- duplicar trabalho indireto no Product Matching (que reutiliza o scrape).

PostgreSQL permanece a fonte de verdade de matching, listings e histórico.

## Problema / decisão necessária

Como compartilhar cache, single-flight e cooldown entre instâncias **sem**
tornar Redis obrigatório nem fonte de verdade, e sem espalhar chamadas Redis
por services/spiders/matching?

## Alternativas consideradas

- Manter só memória local (status quo) — simples, mas inútil com N réplicas
- Redis obrigatório no startup — frágil; quebra a API se Redis cair
- Cache genérico de PostgreSQL / repositories — baixo retorno vs. live fetch
- Fila (Celery/RQ) + workers — fora de escopo; muda a arquitetura de request
- Redis como SoT de ofertas — rejeitado; viola o modelo relacional atual

## Decisão

Adotar Redis como **otimização fail-open** atrás do `ScrapeGuard`:

1. **Cache-aside L1+L2**: memória do processo (L1) + Redis (L2), envelope JSON
   versionado (`schema_version` + `kind`), sem `pickle`
2. **Chaves versionadas** `scout:v1:...` com hash SHA-256 da URL canônica
3. **Distributed single-flight**: `SET NX PX` + token de ownership + Lua
   compare-and-delete; followers fazem poll do cache (não adquirem cooldown)
4. **Distributed cooldown** URL/domínio: `SET NX EX` + `PTTL` antes do live
   fetch (protege egress, não só cache miss)
5. **Fail-open**: qualquer `RedisError`/timeout → fallback aos mecanismos
   locais; nunca HTTP 500 só porque Redis caiu
6. Redis no Compose em modo cache (`appendonly no`, `allkeys-lru`); sem volume
   persistente — estado reconstruível

`ProductScrapeService` / `OfferScrapeService` / matching **não** falam com
Redis diretamente.

### Evolução futura de TTL (não nesta entrega)

- identity cache: TTL longo (horas)
- offer/price cache: TTL curto (minutos) — hoje ambos usam
  `SCRAPE_RESULT_CACHE_TTL_SECONDS=300`
- SERP cache: TTL muito curto
- negative cache seletivo

## Justificativa

O maior retorno operacional está em **evitar live fetch** (Camoufox, proxy,
tráfego, WAF), não em economizar queries PostgreSQL. Encapsular no ScrapeGuard
preserva a arquitetura e os contratos HTTP atuais.

## Consequências positivas

- Várias réplicas compartilham cache/locks/cooldowns
- Restart da API ainda serve hit Redis dentro do TTL
- API continua sem Redis (dev local / degradação)
- Precedência `ProductPriceItem` > `ProductOffer` preservada

## Trade-offs / consequências negativas

- Possível brief stampede se Redis e L1 falharem juntos
- Cooldown/lock dependem de relógio/TTL do Redis (locks nunca eternos)
- Observabilidade via logs estruturados (sem Prometheus nesta fase)
- Dois processos podem brevemente divergir se Redis oscilar (fail-open local)
