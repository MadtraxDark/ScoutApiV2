# Baseline live — Pichau Ryzen 7 5800X3D PDP

**Data:** 2026-09-22 (fetch UTC ~2026-09-23 01:36–01:39)  
**URL:** https://www.pichau.com.br/processador-amd-ryzen-7-5800x3d-8-core-16-threads-3-4ghz-4-5ghz-turbo-cache-100mb-am4-100-100000651pof  
**Escopo:** evidência live **sem** alterar spider/código de scraper.  
**Artefatos:** `data/_pichau_ryzen_live.html` (~657 KB), `memory/working/_pichau_analysis_snips.json`

## 1) HTTP fetch (curl / Invoke-WebRequest)

| Método | Status | Redirects | Size | Content-Type | Notas |
|---|---|---|---|---|---|
| `Invoke-WebRequest` | — | — | — | — | Falhou: conexão fechada inesperadamente |
| `curl.exe -L` (UA Chrome) | **403** | 0 | **6077** B | `text/html; charset=UTF-8` | Cloudflare managed challenge (`Cf-Mitigated: challenge`, `Server: cloudflare`, título "Just a moment...") |

Conclusão HTTP puro: **bloqueado por Cloudflare**. Não é a PDP.

## 2) Fetch pós-challenge (browser Cursor, sem auth inventada)

Após passar o challenge no browser embutido, `document.documentElement.outerHTML` foi exportado via CDP.

| Campo | Valor |
|---|---|
| Status efetivo (página PDP) | **200** (documento carregado; título do produto) |
| HTML size | **657 098 bytes** / **655 235 chars** |
| Content-Type | HTML renderizado (`text/html`; outerHTML) |
| Salvo em | `data/_pichau_ryzen_live.html` (&lt; 2 MB) |

## 3) Marcadores no HTML

| Marcador | Presente? | Count / índice (approx) |
|---|---|---|
| JSON-LD `application/ld+json` | sim | 7 ocorrências; 5 blocks parseáveis |
| `__next_f` / RSC | **sim** | 38 |
| `"product":` (não escapado) | **não** | 0 |
| `\"product\":` (escapado em string RSC) | **sim** | 1× `\"product\":` @ ~287 344 |
| `avista` | sim | 3 (no blob; UI também tem "à vista") |
| `pichau_prices` | **sim** | 1 @ ~288 890 |
| `marcas_info` | **sim** | 1 @ ~287 889 |
| `caracteristicas` | sim | 2 (valor `null` no blob) |
| `sku` / `100-100000651` | sim | sku~11; fragmento SKU 94; `100-100000651POF` 56 |

### Escaped vs unescaped product blob

- **Existe blob RSC escapado:** `self.__next_f.push([1,"...{\"product\":{\"id\":66151,\"sku\":\"100-100000651POF\",..."])`
- **Não há** `"product":` literal unescaped no HTML salvo.
- O produto vive **dentro** de uma string serializada do Flight/RSC (`__next_f`), com aspas escapadas como `\"`.

Snippet (escapado):

```text
self.__next_f.push([1,"6:[[\"$\",\"$L12\",null,{\"product\":{\"id\":66151,\"sku\":\"100-100000651POF\",\"url_key\":\"processador-amd-ryzen-7-5800x3d-...\",\"name\":\"Processador AMD Ryzen 7 5800X3D...
```

## 4) JSON-LD Product / offers

| Campo | Valor |
|---|---|
| `@type` | `Product` |
| `sku` | `100-100000651POF` |
| `offers.price` | **2517.64** |
| `offers.priceCurrency` | `BRL` |
| `offers.availability` | `https://schema.org/InStock` |

Outros JSON-LD: `BreadcrumbList`, `WebSite`, `Organization`.

## 5) Preços no blob `pichau_prices` (RSC)

Dentro do mesmo push `__next_f` (ainda escapado):

| Campo | Valor |
|---|---|
| `special_price` | 2517.64 |
| `pichau_prices.avista` | **2139.99** |
| `avista_discount` | **15** |
| `avista_method` | **PIX** |
| `base_price` | 3294.11 |
| `final_price` | 2517.64 |
| `max_installments` | 12 |
| `min_installment_price` | 209.8 |

Produto: `id=66151`, `sku=100-100000651POF`, `marcas_info.name=AMD`, `caracteristicas=null`, DC `santa-catarina`.

**Implicação para parser:** preço “cartão/final” alinhado ao JSON-LD (**2517.64**); preço à vista/PIX (**2139.99**) só no blob Magento-like `pichau_prices`, não no JSON-LD `offers.price`.

## 6) APIs óbvias descobertas (sem inventar auth)

Observadas no network do browser (sessão pós-CF):

1. `GET /api/request/openbox?id=66151`
2. `GET /api/request/product-review-v2?id=66151&...`
3. `GET /api/request/installments?cartSubtotal=2517.64&...&productId=66151&discountBy=product`

| Endpoint | curl bare | browser `fetch` (cookies CF) |
|---|---|---|
| openbox | **403** CF HTML ~5.7 KB | **200** `{"items":[],"__typename":"Products"}` |
| product-review-v2 | **403** | **200** JSON reviews (4× 5★) |
| installments | **403** | **200** JSON parcelas (1x–12x; 1x c/ 10% → 2265.88) |

Não há endpoint Magento `rest/V1/...` nem GraphQL público óbvio no HTML estático; mídia Magento em `media.pichau.com.br/media/catalog/product/...`. Assets Next em `static.pichau.com.br/_next/static/...`.

## 7) Locais-chave (para spider / parser)

| Dado | Onde |
|---|---|
| Título / SKU SEO | `<title>`, meta description, H1 |
| Preço schema | JSON-LD `Product.offers.price` = 2517.64 |
| Preço PIX/avista | RSC `__next_f` → string → `pichau_prices.avista` = 2139.99 |
| Preço final / special | mesmo blob: `special_price` / `final_price` = 2517.64 |
| Product id | blob `product.id` = 66151 |
| Marca | `marcas_info` no blob (+ UI) |
| Disponibilidade schema | JSON-LD InStock |

## Resumo executivo

- **curl status:** 403 (Cloudflare)  
- **HTML útil size:** ~657 KB (browser pós-challenge)  
- **Escaped RSC blob `\"product\":`:** **sim** (único caminho do product blob)  
- **JSON-LD price:** **2517.64 BRL**  
- **avista / PIX:** **2139.99** (15% via PIX)  
- **Pendências restantes:** nenhuma para esta coleta de evidência.

Sanitização: sem cookies/tokens versionados; HTML/API públicos apenas.
