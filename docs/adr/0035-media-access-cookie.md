# ADR 0035: Cookie HttpOnly para autenticação de mídia no browser

- Status: Accepted
- Data: 2026-09-22

## Contexto

A entrega de bytes de produto é um proxy autenticado
(`GET /products/{id}/images/{id}/content`, ADR 0029). O PriceScout renderiza
imagens com `<img src>` / componentes equivalentes. Tags de mídia **não**
enviam `Authorization: Bearer`.

O access token permanece em memória no frontend (não em `localStorage`). O
refresh cookie (`scout_refresh_token`) tem `path=/auth` e não acompanha
requests de `/products/.../content`.

## Problema / decisão necessária

Como autenticar GETs de mídia no browser sem colocar o access token na query
string, sem expor o Google Drive e sem enfraquecer DENY BY DEFAULT nas APIs
JSON?

## Alternativas consideradas

- **Token na query (`?token=`):** rejeitado — vaza em logs, referrer e
  histórico.
- **Blob URL via `fetch`+Bearer em cada componente:** funciona, mas aumenta
  complexidade, flash de placeholder e impede abrir a imagem em nova aba.
- **Signed URL HMAC de curta duração:** válido, porém muda o contrato de
  `display_url` e exige mint/renovação no FE; adiado.
- **Proxy same-origin no Next.js:** exige o access token no servidor Next;
  o token hoje só existe em memória no cliente.
- **Cookie HttpOnly de access no domínio da API (`path=/`), aceito só na
  rota de content:** escolhido.

## Decisão

1. Em login (`/auth/callback`) e refresh (`/auth/refresh`), gravar cookie
   HttpOnly `scout_access_token` com o JWT de access, `SameSite=Lax`,
   `path=/`, `Secure` em production.
2. Em logout, limpar o cookie.
3. `GET .../images/{id}/content` resolve identidade via **Bearer primeiro**,
   depois o cookie de access, depois bypass de dev (`AUTH_REQUIRED=false`).
4. Demais endpoints JSON **continuam Bearer-only** (sem cookie) para não
   abrir CSRF em POST/PATCH/DELETE.
5. Ownership/`products:read` seguem validados no serviço de imagens.

## Justificativa

Alinha com o proxy autenticado (ADR 0029) e com DENY BY DEFAULT (ADR 0023),
permite `<img src>` same-site sem token na URL e mantém mutações protegidas
por Bearer.

## Consequências positivas

- Todas as telas que usam `display_url` / `primary_image_url` passam a
  carregar bytes no browser autenticado.
- Sem exposição do Drive ao frontend.
- Sem access token em query string.

## Trade-offs / consequências negativas

- Cookie de access no `path=/` é enviado em qualquer GET ao host da API;
  apenas a rota de content o consome — outras rotas ignoram.
- SameSite=Lax impede hotlink cross-site (desejável).
- Em `AUTH_REQUIRED=false` (somente não-produção) o content continua
  acessível sem cookie/Bearer via principal de bypass.
