# ADR 0029: Google Drive como object storage de imagens de produto

- Status: Accepted
- Data: 2026-09-21

## Contexto

O crawl já extrai URLs de galeria (ADR 0012), mas o catálogo ScoutApiV2 /
PriceScout não persistia imagens. A integração PriceScout marcava CRUD
Drive/galeria como comportamento de frontend obsoleto. É necessário um
armazenamento de bytes confiável, com revisão humana antes da persistência,
otimização para o frontend e metadados consultáveis sem listar o Drive.

## Problema / decisão necessária

Como armazenar imagens de produto aprovadas, com conta dedicada, sem expor
credenciais ao frontend, preservando o original e servindo AVIF quando pronto?

## Alternativas consideradas

- **Service Account em My Drive comum:** inadequado — SA não é proprietária
  natural de My Drive de usuário; exige gambiarra de compartilhamento.
- **Service Account + Google Workspace Shared Drive:** adequado se a conta for
  Workspace com Shared Drive verdadeiro; não confirmado para a conta dedicada
  atual — documentado como alternativa futura.
- **Drive por usuário (OAuth do login PriceScout):** acopla storage à identidade
  do usuário, complica cleanup/quota e mistura auth de app com auth de storage.
- **GCS / S3:** signed URLs nativas; introduz vendor/custo operacional novo sem
  necessidade imediata.
- **Só URLs externas da loja:** frágil (hotlink, expiração, variação de CDN).

## Decisão

1. **Uma conta Google dedicada** ao PriceScout, administrada pelo sistema.
2. Autenticação via **OAuth 2.0 offline** (`refresh_token` só no backend).
3. Scope preferencial: `https://www.googleapis.com/auth/drive.file`.
4. **Google Drive** = object storage de bytes (original + AVIF).
5. **PostgreSQL** = fonte de verdade da galeria (`product_images`).
6. **Review-before-persist:** crawl/preview só devolve candidatas; upload só
   após aprovação no `POST /products` (ou CRUD posterior).
7. Pipeline: download seguro → validar → original no Drive → metadata → AVIF
   assíncrono → AVIF preferido; original como fallback permanente.
8. Entrega v1: **proxy autenticado** `GET /products/{id}/images/{id}/content`
   (arquivos privados; pasta raiz nunca pública).

## Justificativa

Alinha com DENY BY DEFAULT (ADR 0023), SoT no Postgres (ADR 0021) e custo
controlado sem fila pesada (ADR 0020). Conta dedicada + OAuth offline evita
Service Account em My Drive e isola storage do login do usuário.

## Consequências positivas

- Frontend nunca recebe credenciais Drive.
- Galeria consultável sem listar pastas no Drive.
- Original preservado para fallback e reprocessamento.
- AVIF falho não invalida a imagem.

## Trade-offs / consequências negativas

- Bytes passam pelo backend (latência/quota Drive); CDN fica para o futuro.
- `BackgroundTasks`/thread pool pode perder AVIF em restart — status
  `pending`/`failed` no Postgres permite retry.
- Scope `drive.file` exige que a pasta raiz seja criada/gerida pelo app.
- Alternativa futura: Workspace Shared Drive + Service Account, se confirmado.
