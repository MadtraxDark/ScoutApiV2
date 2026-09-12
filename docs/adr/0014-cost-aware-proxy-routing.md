# ADR 0014: Cost-aware proxy routing and Shopee minimal fetch

- Status: Accepted
- Data: 2026-09-12
- Atualizado: 2026-09-12 (Proxy Cost Mode — todas as lojas em FALLBACK)

## Contexto

DataImpulse (proxy residencial) cobra principalmente por tráfego transferido (GB).
O `CamoufoxHtmlFetcher` compartilhado aplicava `CAMOUFOX_PROXY_URL` a **todas** as
lojas, fazendo Magazine Luiza, KaBuM, Best Buy e Nissei consumirem egress pago
mesmo sem bloqueio. Na Shopee, cada scrape pagava warm-up da home + PDP completa
(networkidle), incluindo imagens, mídia e fontes — medição baseline ~18,5 MB e
~636 requests, com ~12,5 MB **depois** de capturar `get_pc`.

## Problema / decisão necessária

Como minimizar `cost / traffic per successful scrape` sem prejudicar spiders,
sem hardcode de preço DataImpulse e sem espalhar `if store == "shopee"` pelos
services?

## Alternativas consideradas

- Manter proxy global + otimizar só o parser (`include_images=false`)
- Um único Camoufox com proxy opcional por request (não suportado no contexto)
- Proxy store-aware (REQUIRED / FALLBACK / DIRECT) + dual fetchers + early-stop
- Blacklist grande de hosts de analytics sem evidência

## Decisão

1. **Proxy Cost Mode (regra permanente do projeto):**
   - Proxy pago evitado sempre que possível
   - **Todas** as lojas (incluindo Shopee) → `ProxyPolicy.FALLBACK`
     (direct primeiro; proxy só após `RequestError.code == UPSTREAM_BLOCKED`)
   - `ParseError` / erros de parsing **nunca** disparam fallback
   - Proxy ativo = tráfego mínimo (bloquear `image`/`media`/`font`; ignorar
     `include_images=true` com `images_omitted: proxy-cost-mode`)
2. **Dual Camoufox:** perfil `direct` e perfil `default` (proxied / seed),
   orquestrados por `StoreAwareHtmlFetcher`.
3. **Shopee minimal fetch:** capturar `/api/v4/pdp/get_pc`, early-stop (sem
   networkidle), warm-up `once_per_session`, `supports_images=false`.
4. **Cache de `ProductOffer`** no `ScrapeGuard` + single-flight por URL canônica.
5. **Métricas** `fetch_cost_metrics` — dashboard DataImpulse permanece a fonte
   financeira.

Trade-off Playwright: `page.route` desativa HTTP cache; no probe Shopee o
bloqueio de mídia ainda reduziu ~90% do tráfego vs cache sem routing.

## Justificativa

Medições controladas mostraram early-stop + resource blocking com grande queda
de GB. Direct-first em todas as lojas evita faturar egress no caminho feliz;
proxy só quando o acesso classificado falha.

## Consequências positivas

- Proxy deixa de ser global e deixa de ser obrigatório na Shopee
- `/crawl/offer` cacheia dentro do TTL
- Telemetria permite calcular custo por scrape bem-sucedido
- Galeria omitida sob proxy cost mode / política Shopee

## Trade-offs / consequências negativas

- Direct Shopee pode falhar com mais frequência → um fallback pago pontual
- Routing Playwright vs HTTP cache (aceito no caminho proxied)
- Warm-up `once_per_session` pode falhar se o profile ficar “frio”
- TTL de cache: maior TTL → menor custo, preço potencialmente mais antigo
