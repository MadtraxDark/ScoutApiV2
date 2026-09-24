# PENDING-021 — Ativar e validar o fluxo de logos no ambiente integrado

- Status: IN_PROGRESS
- Tipo: TESTING
- Prioridade: P1
- Área: matching/store-admin
- Origem: 2026-09-24 — upload de logos raster e otimização AVIF
- Atualizado: 2026-09-24

## Contexto

O código de upload, storage, fila, entrega e preview foi implementado. A
migration `0030_store_logo_media` foi aplicada no PostgreSQL do Compose após
autorização do usuário. API e worker foram reconstruídos e recriados com as
alterações durante esta tarefa.

## Feito

- Validação de SVG, PNG, WebP, AVIF, JPG e JPEG por conteúdo, MIME, extensão,
  limite de 2 MB e dimensões raster.
- Storage Drive e worker reutilizam o `AvifOptimizer` e o scheduler de imagens.
- Fallback do original, estado de falha, proteção por versão contra jobs antigos
  e recuperação de jobs `processing` antigos.
- Preview local imediato para SVG, PNG, WebP, AVIF e JPEG; URLs anteriores são
  revogadas ao trocar arquivo ou fechar o editor. Cancelar não envia o arquivo.
- Erro de upload mantém modal, arquivo e preview local para nova tentativa.
- Original continua visível durante a conversão; as telas de lojas/ofertas
  consultam estados `pending`/`processing` e atualizam quando a AVIF fica pronta.
- URLs distinguem por versão e variante original/AVIF para evitar servir a
  variante anterior do cache do navegador.
- Testes unitários para formatos, alpha, falha, idempotência, concorrência e
  regressão das imagens de produto.
- Smoke Playwright com dados de API simulados: formatos, cancelamento,
  reabertura, falha/retenção, seleções consecutivas, troca automática em lojas e
  ofertas persistidas.
- Migration aplicada; `alembic current` reportou `0030_store_logo_media (head)`
  e a inspeção confirmou as seis novas colunas.
- API e worker reconstruídos/recriados; o startup confirmou `alembic_upgrade_head`
  concluído e a API ficou saudável.
- Smoke sem interceptação contra API e banco reais: logo persistida da KaBuM
  respondeu `200 image/avif`, com ETag variante/versionada, e carregou na lista
  de lojas e na seção de ofertas persistidas após o restart.
- O healthcheck HTTP herdado do Dockerfile apontava o worker para `/health`,
  embora o worker não tenha servidor HTTP. O Compose agora desabilita esse
  healthcheck incorreto para `image-optimizer`.

## Falta

- Validar um novo upload/reabertura após restart da API e worker com Drive real;
  esse teste foi preservado para não substituir a logo cadastrada no ambiente.
- Confirmar que a nova URL funciona com o cookie de mídia no domínio de deploy.

## Por que não terminou

O primeiro comando local não resolvia o hostname `postgres`. Após autorização do
usuário, a migration foi aplicada no container conectado à rede do Compose.
Depois, API e worker foram recriados. O teste de upload contra Drive real ficou
de fora para não sobrescrever a logo KaBuM já persistida; o domínio de deploy
também não está disponível nesta validação local.

## Impacto

O schema e os serviços locais estão atualizados. O healthcheck HTTP do worker foi
desabilitado porque esse processo não atende `/health`; a API continua com seu
healthcheck. A persistência pós-restart da logo existente foi validada, mas não
houve novo upload no Drive nem validação no domínio de deploy.

## Relacionado

- `alembic/versions/0030_store_logo_media.py`
- `docs/adr/0042-store-logo-media-processing.md`
- `tests/unit/test_store_metadata.py`
- `tests/unit/test_store_logo_worker.py`

## Pronto quando

Upload e reabertura após restart validados com Drive real, e nova URL confirmada
no domínio de deploy; os testes locais de persistência e smoke contra a API real
já foram concluídos.
