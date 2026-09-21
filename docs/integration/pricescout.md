# Integração PriceScout ↔ ScoutApiV2

Documento canônico da matriz de integração. Fonte de verdade da API:
OpenAPI (`/openapi.json`) + schemas Pydantic + routers.

Frontend: repositório PriceScout (Next.js). Backend: este repositório.

## Arquitetura

```text
PriceScout (localhost:3000)
  → utils/api (client + Bearer + refresh single-flight)
  → ScoutApiV2 (localhost:8000)
  → Services → PostgreSQL / Crawler / Camoufox
```

## Matriz de operações

| Frontend operation | Endpoint legado FE | ScoutApiV2 | Status | Action |
|---|---|---|---|---|
| health / config | — | `GET /health` | DIRECT_MAPPING | usar health |
| Google login start | `GET /api/v1/auth/google/login` | `GET /auth/google` | FRONTEND_ADAPTER | `authorization_url` |
| OAuth callback | `GET /api/v1/auth/google/callback` | `GET /auth/callback` | FRONTEND_ADAPTER | fragment `#access_token` |
| auth me | `GET /api/v1/auth/me` | `GET /auth/me` | FRONTEND_ADAPTER | `id`+`display_name`; UI autenticada (sem role) |
| auth refresh | `POST /api/v1/auth/refresh` | `POST /auth/refresh` | FRONTEND_ADAPTER | cookie + Bearer |
| auth logout | `POST /api/v1/auth/logout` | `POST /auth/logout` | DIRECT_MAPPING | limpar access em memória |
| email/password/magic | `/api/v1/auth/login|signup|…` | — | OBSOLETE_FRONTEND_BEHAVIOR | remover |
| catalog overview | `GET /api/v1/catalog/overview` | — | FRONTEND_ADAPTER | derivar de `GET /products` |
| list products | `GET /api/v1/catalog/products` | `GET /products` | BACKEND_ENDPOINT_REQUIRED | listagem paginada |
| product search | filtros FE | `GET /products/search` | DIRECT_MAPPING | integrar filtros reais |
| product detail | `GET /api/v1/catalog/products/{id}` | `GET /products/{id}` | FRONTEND_ADAPTER | mapper `ProductView` |
| product update | `PATCH …/products/{id}` | `PATCH /products/{id}` | BACKEND_ENDPOINT_REQUIRED | schema explícito |
| product delete | `DELETE …/products/{id}` | `DELETE /products/{id}` | BACKEND_ENDPOINT_REQUIRED | ownership + cascade |
| preview | `POST …/preview` | `POST /crawl` | FRONTEND_ADAPTER | mapper preview |
| get/discard preview | preview TTL | — | OBSOLETE_FRONTEND_BEHAVIOR | estado local FE |
| import | `POST …/import` | `POST /products` | FRONTEND_ADAPTER | `ProductRegisterRequest` |
| other-store prices | `POST …/other-store-prices` | `POST /match` | FRONTEND_ADAPTER | URL de listing |
| other-store stream | SSE variants | `POST /match/stream` | DIRECT_MAPPING | SSE real (1 execução) + refresh prévio |
| other-store refresh | (fase stream legado) | `POST /offers/refresh` | DIRECT_MAPPING | antes do match no FE |
| offers refresh | — | `POST /offers/refresh` | DIRECT_MAPPING | integrar |
| list stores | `GET …/catalog/stores` | `GET /stores` | BACKEND_ENDPOINT_REQUIRED | registry crawler |
| create/update store | POST/PATCH stores | — | OBSOLETE_FRONTEND_BEHAVIOR | somente leitura |
| store markets | `GET …/store-markets` | derivado de `/stores` | FRONTEND_ADAPTER | countries do registry |
| images CRUD | Drive/gallery APIs | `GET/POST/PATCH/DELETE /products/{id}/images` + `/content` | DIRECT_MAPPING | galeria pós-aprovação; `display_url` |
| crawl offer | — | `POST /crawl/offer` | DIRECT_MAPPING | opcional FE |

## Decisões

### Access token

Mantido **somente em memória** no módulo `utils/api/auth.ts`.
Refresh permanece HttpOnly (`scout_refresh_token`, path `/auth`).
Em reload da página: `POST /auth/refresh` (credentials) → novo access em memória.
Não usar `localStorage` para access token.

### `/auth/me` e admin UI

`PublicUser` continua mínimo (`id`, `display_name`) — ADR 0023.
Gate `/admin` exige **usuário autenticado**, não `role=admin`.
Autorização real = permissões JWT no backend.

### Preview

Sem cache persistido no backend nesta integração. Preview = resultado de
`POST /crawl` mantido no estado do cliente até import ou descarte.

O frontend expõe o checkbox **Buscar imagens do produto** depois que a URL
casa com uma loja do `GET /stores`. O default vem de
`default_include_images` / `image_fetch_cost` do registry (não de `if store ==`
no FE). Envia `include_images` real no body.

### Imagens

Crawl/preview (`POST /crawl` com `include_images=true`) devolve
`image_candidates` (URLs externas) — **não** persiste no Drive.
Falha de galeria não derruba o produto: metadata `image_status` /
`image_error` / `image_pipeline` permite UX de sucesso parcial.

Após revisão no PriceScout, o import (`POST /products`) envia
`images: [{ source_url, position, is_main }]`. Só então o ScoutApiV2 baixa,
valida (SSRF), grava o **original** no Drive e responde sucesso. AVIF roda
em background (`optimized_status=pending` é estado válido).

Galeria persistida: usar `display_url` ou, na listagem, `primary_image_url`
(ambos já aplicam AVIF-if-ready, senão original). Não usar URL da loja depois
da aprovação. Credenciais Drive nunca no frontend.

Canônico: [`docs/persistence/product-images.md`](../persistence/product-images.md)
+ [ADR 0029](../adr/0029-google-drive-product-images.md).

### Checklist frontend (PriceScout)

1. Após URL reconhecida: mostrar checkbox; default = `default_include_images`
   da loja.
2. Preview: `POST /crawl` com `include_images` conforme checkbox; UI usa
   `image_candidates` (ou `images[]` URLs) como candidatas externas.
3. Se `image_status` for `error`/`empty`/`omitted` com produto OK: avisar
   “Produto encontrado, mas não foi possível carregar a galeria.”
4. Permitir selecionar / remover / reordenar / marcar principal **antes** do
   import; deixar claro que ainda não estão no Drive.
5. Import: `POST /products` com `images: [{ source_url, position, is_main }]`
   das aprovadas (idempotente no clique).
6. Após cadastro: listar via `GET /products/{id}/images` ou campo `images` /
   `primary_image_url` do `ProductView`; renderizar `display_url` /
   `primary_image_url` (com Bearer). **Não espere AVIF** — original já é
   válida enquanto `optimized_status` for `pending`/`processing`/`failed`.
7. CRUD: `POST/PATCH/DELETE /products/{id}/images`; retry AVIF opcional.
8. Não enviar `drive_file_id` / paths / credentials no body.
9. Reutilizar `ImageViewer` / `ImageWithState` se já existirem.

### Progresso Match

`POST /match/stream` emite SSE na **mesma** execução do match (sem segunda
chamada). Eventos: `store_started`, `searching`, `candidates_found`,
`scraping_candidate`, `matched`, `no_match`, `error`, `completed`.

Fluxo PriceScout do botão **Buscar preços em outras lojas**:

1. `POST /offers/refresh` — atualiza snapshots das ofertas já persistidas
2. `POST /match/stream` — descoberta em outras lojas (execução única SSE)
3. `GET /products/{id}` — recarrega ofertas persistidas na UI

Regras:

- `reference_url` vem da listing mais confiável (URL canônica, disponível,
  com preço, preferindo a loja de origem) — nunca `variants[0]` cego.
- A loja de referência **não** entra na descoberta (“outras lojas”).
- `SEARCH_UNSUPPORTED` → `errors[]` (nunca `unmatched_stores`).
- Import (`POST /products`) pode enviar `price` / `pix_price` /
  `original_price` do preview para seed do `OfferSnapshot` inicial.
- `persist=true` e `include_review=true` no fluxo de busca do painel.
- O FE envia `canonical_product_id` no match para persistir no mesmo
  produto da página (evita duplicata / reparent silencioso de listing).

## CORS

Origens explícitas (`CORS_ALLOWED_ORIGINS`), `credentials=true`, métodos
`GET, POST, PATCH, DELETE, OPTIONS`, headers `Authorization, Content-Type, Accept`.
