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
| other-store stream | SSE variants | `POST /match/stream` | BACKEND_ENDPOINT_REQUIRED | SSE real (1 execução) |
| offers refresh | — | `POST /offers/refresh` | DIRECT_MAPPING | integrar |
| list stores | `GET …/catalog/stores` | `GET /stores` | BACKEND_ENDPOINT_REQUIRED | registry crawler |
| create/update store | POST/PATCH stores | — | OBSOLETE_FRONTEND_BEHAVIOR | somente leitura |
| store markets | `GET …/store-markets` | derivado de `/stores` | FRONTEND_ADAPTER | countries do registry |
| images CRUD | Drive/gallery APIs | — | OBSOLETE_FRONTEND_BEHAVIOR | sem persistência; empty state |
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

### Imagens

ScoutApiV2 extrai URLs opcionais no crawl (`include_images`); não há CRUD
Drive/galeria. UI de galeria editável fica desabilitada / empty state.

### Progresso Match

`POST /match/stream` emite SSE na **mesma** execução do match (sem segunda
chamada). Eventos: `store_started`, `searching`, `candidates_found`,
`scraping_candidate`, `matched`, `no_match`, `error`, `completed`.

## CORS

Origens explícitas (`CORS_ALLOWED_ORIGINS`), `credentials=true`, métodos
`GET, POST, PATCH, DELETE, OPTIONS`, headers `Authorization, Content-Type, Accept`.
