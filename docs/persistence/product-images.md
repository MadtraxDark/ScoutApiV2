# Imagens de produto — Google Drive + PostgreSQL

Documento canônico do lifecycle de imagens do catálogo.
Decisão: [ADR 0029](../adr/0029-google-drive-product-images.md).
Integração FE: [pricescout.md](../integration/pricescout.md).

## Princípio

```text
Crawler encontra candidatas
  → PriceScout revisa / seleciona / ordena / define principal
  → ScoutApiV2 baixa só as aprovadas
  → original no Drive + metadata no Postgres
  → AVIF assíncrono
  → API prefere AVIF; original é fallback
```

**EXTERNAL CANDIDATE IMAGE ≠ CATALOG PRODUCT IMAGE.**  
Upload no Drive só ocorre **após aprovação**.

## Conta dedicada

- Uma conta Google exclusiva do PriceScout.
- OAuth 2.0 administrativo (offline); usuários finais **não** autorizam Drive.
- Credenciais só no backend: `GOOGLE_DRIVE_CLIENT_ID`,
  `GOOGLE_DRIVE_CLIENT_SECRET`, `GOOGLE_DRIVE_REFRESH_TOKEN`,
  `GOOGLE_DRIVE_ROOT_FOLDER_ID`.
- Scope: `https://www.googleapis.com/auth/drive.file`.
- Bootstrap one-shot: `python scripts/google_drive_oauth_bootstrap.py`.
  - Preferir OAuth client tipo **Desktop app** no Google Cloud Console
    (APIs e serviços → Credenciais → Criar credenciais → ID do cliente OAuth
    → **Aplicativo para computador**). Atualize `GOOGLE_DRIVE_CLIENT_ID` /
    `GOOGLE_DRIVE_CLIENT_SECRET` no `.env` com esse cliente.
  - Se usar client **Web**: em "URIs de redirecionamento autorizados" adicione
    exatamente (barra final obrigatória):
    `http://127.0.0.1:8765/` e `http://localhost:8765/`
    (erro `400: redirect_uri_mismatch` = URI ausente, barra faltando, ou
    client_id errado — tipicamente o do login Supabase).
  - Não reutilizar o client_id do login Supabase/PriceScout.

Não use o Google OAuth do login Supabase do usuário para storage.

## Organização no Drive

```text
{ROOT_FOLDER}/
└── products/
    └── <product_uuid>/
        ├── original/
        │   └── <image_uuid>.<ext>
        └── optimized/
            └── <image_uuid>.avif
```

Identidade = UUID interno. Identificador de arquivo = `drive_file_id`.

## Schema `product_images`

PostgreSQL conhece: produto → imagens → file IDs original/AVIF, status,
hash, dimensões, `position`, `is_main`. A API **não** lista o Drive para
montar a galeria.

### Status

| Campo | Valores |
|---|---|
| `original_status` | `pending`, `downloading`, `ready`, `failed`, `deleting` |
| `optimized_status` | `pending`, `processing`, `ready`, `failed` |

## Pipeline

1. Validar URL (http/https) + SSRF (DNS→IP, redirects revalidados).
2. Download com limite de bytes/timeout/redirects.
3. Validar conteúdo real (Pillow), não só `Content-Type`.
4. SHA-256; dedup por `(product_id, sha256)`.
5. Upload original → `original_status=ready`.
6. Enfileirar AVIF (thread pool, concorrência limitada).
7. AVIF ready → preferido em `display_url` / `/content`.

Falha de AVIF: original permanece; `optimized_status=failed`; retry via
`POST .../retry-optimization`.

## Entrega

`GET /products/{product_id}/images/{image_id}/content`

- Auth + ownership.
- Prefere AVIF se `optimized_status=ready`.
- `Cache-Control: private, max-age=…` + `ETag`.
- `display_url` aponta para este endpoint (nunca `drive.google.com/.../view`).

## CRUD

| Método | Path |
|---|---|
| GET | `/products/{id}/images` |
| POST | `/products/{id}/images` |
| PATCH | `/products/{id}/images` |
| DELETE | `/products/{id}/images/{image_id}` |
| POST | `/products/{id}/images/{image_id}/retry-optimization` |

Reorder / set main = só metadata. Delete = remove files conhecidos + linha;
“not found” no Drive é idempotente. Delete de produto limpa imagens conhecidas
antes do cascade (sem delete recursivo cego de pasta).

## Configuração

| Variável | Função |
|---|---|
| `GOOGLE_DRIVE_*` | Credenciais OAuth + pasta raiz |
| `IMAGE_MAX_BYTES` | Tamanho máximo do download |
| `IMAGE_MAX_DIMENSION` | Lado máximo (sem upscale) |
| `IMAGE_DOWNLOAD_TIMEOUT_SECONDS` | Timeout HTTP |
| `IMAGE_MAX_REDIRECTS` | Redirects permitidos |
| `IMAGE_MAX_PER_PRODUCT` | Cap por produto |
| `IMAGE_AVIF_QUALITY` | Qualidade Pillow AVIF |
| `IMAGE_AVIF_MAX_CONCURRENCY` | Conversões paralelas |
| `IMAGE_MEDIA_CACHE_MAX_AGE_SECONDS` | Cache-Control do proxy |

## SSRF

Rejeitar localhost, loopback, redes privadas, link-local, metadata e
redirects que apontem para esses destinos.

## Shared Drive (futuro)

Se a conta passar a usar **Google Workspace Shared Drive** verdadeiro,
avaliar Service Account + Shared Drive. Enquanto for My Drive de conta
comum dedicada, permanece OAuth offline.
