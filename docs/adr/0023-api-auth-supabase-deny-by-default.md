# ADR 0023: Autenticação API via Supabase Auth + deny-by-default

- Status: Accepted
- Data: 2026-09-14

## Contexto

A API ScoutApiV2 expunha crawler, matching e persistência sem autenticação de
cliente. Há risco de abuso de recursos (browser/proxy), BOLA em produtos e
vazamento de dados. O projeto já usa Supabase Postgres (ADR 0021) e o frontend
deve autenticar via Google através do Supabase Auth.

## Problema / decisão necessária

Como autenticar e autorizar clientes da API sem inventar IdP próprio, sem
enviar secrets privilegiados ao frontend, e com rate limiting adequado a
múltiplas instâncias?

## Alternativas consideradas

- **A — Auth caseira (usuário/senha + JWT próprio):** custo de segurança alto;
  duplica IdP.
- **B — Supabase Auth + validação JWT na API (JWKS):** reutiliza IdP; access
  token Bearer; refresh HttpOnly no BFF.
- **C — Validar todo request com `GET /auth/v1/user`:** latência e acoplamento
  ao Auth server; pior que JWKS local.
- **D — SlowAPI only in-memory:** insuficiente com várias réplicas; Redis já
  existe (ADR 0020).
- **E — Serviço pago de WAF/Auth:** rejeitado sem necessidade (OSS suficiente).

## Decisão

Adotar **B**:

1. DENY BY DEFAULT em todos os routers de negócio.
2. Allowlist pública: `/health` e rotas `/auth/*` de sessão (google, callback,
   refresh, logout). `/auth/me` exige Bearer.
3. Validar JWT com `PyJWT` + JWKS (`ES256`/`RS256`); HS256 só com
   `SUPABASE_JWT_SECRET` para testes/legado.
4. Autorização separada (`require_permission` / `require_admin`) e ownership
   via `canonical_products.owner_user_id` = JWT `sub`.
5. Rate limit Redis-first + fallback memória (`RateLimiter`), escopos
   `default` / `auth` / `crawler`.
6. Schemas públicos whitelist (`PublicUser`); redaction de logs; erros
   sanitizados; CORS explícito; OpenAPI desligado em production.

## Justificativa

Alinha ao IdP já escolhido (Supabase), segue FastAPI dependencies, OWASP API
Top 10 (auth, BOLA, BOPLA, resource consumption) e Proxy Cost Mode (protege
abuso de crawl sem mudar Camoufox).

## Consequências positivas

- Clientes anônimos não disparam scrape/browser.
- Secrets permanecem server-side (`anon` key só no backend para exchange).
- Testes de segurança cobrem 401/403/429/minimização.
- Multi-instância compartilha contadores via Redis quando configurado.

## Trade-offs / consequências negativas

- Operadores precisam configurar Supabase Auth + Google provider.
- Produtos com `owner_user_id` isolam leitura entre usuários (catálogo legado
  `NULL` permanece legível a autenticados).
- Rate limit fixed-window pode permitir burst na virada do minuto (aceitável;
  limites de crawler são baixos).
