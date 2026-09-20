# Segurança da API — autenticação, autorização e rate limiting

Documento canônico do fluxo de segurança HTTP do ScoutApiV2.
Invariantes curtos: [`AGENTS.md`](../../AGENTS.md) e
[`.cursor/rules/security.mdc`](../../.cursor/rules/security.mdc).
Decisão: [ADR 0023](../adr/0023-api-auth-supabase-deny-by-default.md).

## Arquitetura

```text
Frontend
  → Google OAuth (Supabase Auth, PKCE iniciado em GET /auth/google)
  → access_token (Bearer)
  → ScoutApiV2 valida JWT (JWKS / HS256 teste)
  → AuthenticatedPrincipal (sub, role)
  → require_permission / ownership
  → serviço de domínio
```

Refresh token permanece em cookie HttpOnly (`scout_refresh_token`, path `/auth`).
A `service_role` **nunca** é usada pelo frontend nem retornada pela API.

## Allowlist pública

| Rota | Motivo |
|---|---|
| `GET /health` | Liveness/readiness sem dados sensíveis |
| `GET /auth/google` | Início OAuth |
| `GET /auth/callback` | Callback OAuth/PKCE |
| `POST /auth/refresh` | Renovação via cookie |
| `POST /auth/logout` | Limpa cookies de sessão |

Tudo o mais exige `Authorization: Bearer` (incluindo `GET /auth/me`) quando
`AUTH_REQUIRED=true` (padrão).

### `AUTH_REQUIRED`

| Valor | Comportamento |
|---|---|
| `true` (default) | Endpoints protegidos exigem Bearer válido; 401 se ausente/inválido |
| `false` | Modo local/dev/teste: sem Bearer usa principal fixo `dev-bypass` (`USER`, UUID estável). Bearer presente ainda é validado. Rate limiting, validação e secrets permanecem ativos |

**Produção:** `ENVIRONMENT=production` + `AUTH_REQUIRED=false` (ou alias
`AUTH_ENABLED=false`) **falha no startup** — a API não sobe pública por
acidente de `.env`.

Ownership continua derivando apenas do principal autenticado (ou do principal
de bypass em dev) — nunca de `user_id` no body.

Em `ENVIRONMENT=production`: `/docs`, `/redoc` e `/openapi.json` ficam
desabilitados.

## Endpoints autenticados

| Rota | Permissão | Rate scope |
|---|---|---|
| `GET /auth/me` | autenticado | default |
| `POST /crawl` | `crawl` | crawler |
| `POST /crawl/offer` | `crawl` | crawler |
| `POST /match` | `match` | crawler |
| `POST /offers/refresh` | `offers:refresh` | crawler |
| `POST /products` | `products:write` | default |
| `GET /products/search` | `products:read` | default |
| `GET /products/{id}` | `products:read` | default |

Roles: `user` (permissões de negócio) e `admin` (`AUTH_ADMIN_USER_IDS` ou
`app_metadata.role=admin`).

## Ownership (BOLA)

- `canonical_products.owner_user_id` = JWT `sub` na criação via `POST /products`.
- Leitura/refresh negada (404) se o produto tem dono diferente e o caller não é admin.
- Linhas legadas/`NULL` (matching system) continuam legíveis a usuários autenticados.
- O body **não** aceita `user_id` / `owner_user_id` (`extra=forbid`).

## Minimização

`PublicUser`: apenas `id`, `display_name`.
E-mail, telefone, metadata do provider e roles **não** saem em `/auth/me`.

## Rate limiting

Config (`core/config.py`):

- `RATE_LIMIT_ENABLED`
- `RATE_LIMIT_DEFAULT_PER_MINUTE`
- `RATE_LIMIT_AUTH_PER_MINUTE`
- `RATE_LIMIT_CRAWLER_PER_MINUTE`

Backend: Redis quando `REDIS_URL` está definido; senão memória do processo.
Identidade: hash do Bearer (usuário) ou IP (auth público). `X-Forwarded-For`
só se o peer estiver em `TRUSTED_PROXY_IPS`.

Resposta ao exceder: **429** + `Retry-After`.

Throttling por domínio de marketplace (ScrapeGuard) é **ortogonal** a este
controle.

## CORS

`CORS_ALLOWED_ORIGINS` = lista CSV explícita. Wildcard `*` é ignorado/rejeitado
com credentials.

## Logs e erros

- `core/log_redaction.py` — Authorization, tokens, URLs com senha, etc.
- Handlers em `core/http_errors.py` — sem stack/SQL/secrets na resposta.

## Variáveis

Ver `.env.example` (valores vazios; nunca secrets reais).

Relevantes para auth:

- `AUTH_REQUIRED` (default `true`; alias legado `AUTH_ENABLED`)
- `ENVIRONMENT` (produção rejeita `AUTH_REQUIRED=false` no startup)
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_*`
- `AUTH_ADMIN_USER_IDS`, `CORS_ALLOWED_ORIGINS`, `TRUSTED_PROXY_IPS`
- `RATE_LIMIT_*`

## Testes

`tests/unit/test_security.py` — 401/403/429, `alg=none`, minimização, redaction,
CORS, admin gate, `AUTH_REQUIRED=true/false`, rejeição em production.
