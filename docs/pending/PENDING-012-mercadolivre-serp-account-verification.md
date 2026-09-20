# PENDING-012 — Mercado Livre SERP account-verification (auth wall)

- Status: OPEN
- Tipo: INCOMPLETE
- Prioridade: P1
- Área: crawler/mercadolivre
- Origem: 2026-09-20 — validação identity-only Gigabyte RTX 5060
- Atualizado: 2026-09-20

## Contexto

Discovery identity-only (`Gigabyte GeForce RTX 5060`) encontrou KaBuM e
AliExpress organicamente, mas a SERP do Mercado Livre
(`lista.mercadolivre.com.br/{query}`) redireciona para
`/gz/account-verification` (“Olá! Para continuar, acesse sua conta”).

Antes da correção, o HTML de verificação era parseado como SERP vazia →
falso `SEARCH_FAILURE` / `NO_MATCH`. Agora classifica-se como auth wall.

## Feito

- Detecção de `account-verification` em `is_auth_wall_page`.
- HTTP-first aceita SERP `ui-search` sem exigir PDP.
- Spider `parse_search_results` rejeita HTML de verification (`ParseError`).
- Login ML no `ChallengeResolver` (`MERCADOLIVRE_AUTH_*`) + param `go` no resume URL.
- Query progressiva identity-only + regressões GPU/form-factor.

## Falta

- Validação live da SERP ML com sessão autenticada do operador
  (`MERCADOLIVRE_AUTH_EMAIL` / `MERCADOLIVRE_AUTH_PASSWORD` preenchidos) ou
  profile Camoufox já logado.
- Confirmar descoberta orgânica de oferta Gigabyte RTX 5060 no ML após login.

## Por que não terminou

- Ambiente atual sem credenciais ML no `.env`.
- API pública `sites/MLB/search` → 403.
- Proxy residencial HTTP ainda cai em `account-verification`.
- Googlebot UA também cai em verification (não adotado).

## Investigação

### Causa conhecida

- Soft-auth gate do Mercado Livre em tráfego suspeito na lista pública;
  página pede login explícito (não é Snoopy PoW).

### O que foi testado

- curl_cffi direct → `account-verification` → agora `AUTH_REQUIRED`.
- curl_cffi + `CAMOUFOX_PROXY_URL` → mesmo gate.
- curl_cffi + `__cr.br` → timeout.
- Googlebot UA → mesmo gate.
- API `api.mercadolibre.com/sites/MLB/search` → 403.
- Camoufox (direct+proxy) sem credenciais → hang longo / soft-wait genérico
  (corrigido para login ML dedicado + fail-fast sem credenciais).

### Fontes consultadas

- Docs: ADR 0018, `docs/crawler/stores/mercadolivre.md`, ADR 0025.
- OSS: Apify `mercado-livre-brasil-scraper` (API → HTML; challenge fail-closed),
  `devAlphaSystem/ML-Search-CLI`, `rodrigopg/mcp-brazil-marketplaces` (Googlebot UA).
- Artigos 2026: scraping ML / account-verification / residential BR.

### Alternativas avaliadas / descartadas

- API MLB search — 403 sem app token.
- Googlebot spoof — ainda verification; risco ético/ToS.
- Hardcode URL MLB — invalida o teste de discovery.
- Baixar threshold do matcher — não resolve SEARCH.

### Por que nenhuma opção segura/viável resolveu agora

- Gate exige sessão/login do operador; credenciais não configuradas neste ambiente.

### Referências úteis

- ADR 0018 / `.cursor/rules/auth-wall-resolution.mdc`
- `scripts/_live_gigabyte_rtx5060_identity.py`
- Report: `data/live-match-reports/gigabyte_rtx5060_identity_20260920T142423Z.json`

### Condição para continuar

- Operador configura `MERCADOLIVRE_AUTH_EMAIL` + `MERCADOLIVRE_AUTH_PASSWORD`
  (ou seed de profile Camoufox logado) e reexecuta o script identity-only
  só para `mercadolivre`.

## Impacto

- Match identity-only reporta ML como ERROR/`AUTH_REQUIRED` (correto),
  não como ausência do produto.
- Ground-truth visual ML ainda sem MATCH live nesta sessão.

## Relacionado

- `src/scout_api/modules/crawler/services/html_fetcher.py`
- `src/scout_api/modules/crawler/services/challenge_resolution.py`
- `src/scout_api/modules/crawler/services/mercadolivre_http_first_fetcher.py`
- `src/scout_api/modules/crawler/spiders/brazil/mercadolivre.py`

## Pronto quando

- SERP `gigabyte rtx 5060` (ou query progressiva equivalente) retorna
  candidatos `/p/MLB…` sem URL pré-fornecida; matcher aceita oferta
  Gigabyte RTX 5060 (variant opcional).
