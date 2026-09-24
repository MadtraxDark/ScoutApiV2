# ADR 0042: Upload e otimização de logos das lojas

- Status: Accepted
- Data: 2026-09-24
- Supersedes: parte da política de logos do ADR 0041

## Contexto

O painel persistia somente texto SVG em `store_metadata.logo_svg`. A
infraestrutura `images` já oferece storage privado no Google Drive e conversão
Pillow para AVIF em worker periódico, com o original disponível durante o
processamento.

## Decisão

Manter SVG validado inline, aceitar PNG, WebP, AVIF, JPG e JPEG até 2 MB via
upload multipart. Os raster são verificados por conteúdo real e MIME e salvos
no storage Drive usado por imagens de produto. PNG, WebP e JPEG ficam
`pending` e passam pelo `AvifOptimizer` no worker existente; AVIF e SVG ficam
`ready` sem reconversão. A API entrega a variante AVIF quando pronta e mantém
o original como fallback.

Cada upload possui versão própria. O worker só publica seu resultado se a
versão ainda for a atual; jobs `processing` abandonados são recuperados após
cinco minutos. Uma falha registra `failed` e preserva o original. A substituição
confirma primeiro o novo arquivo e a referência no banco e só então remove
arquivos anteriores.

O editor mantém a seleção como preview local até o salvamento confirmado. Cada
seleção nova substitui e revoga o `Object URL` anterior; cancelar não envia o
arquivo. Após o upload, o original é a variante servida enquanto a otimização
estiver pendente ou falhar. Telas que exibem logos persistidas consultam o
estado até a fila chegar a um estado terminal.

As URLs de mídia incluem a versão da logo e distinguem `original` de `avif`.
Essa chave separa as entradas de cache: quando o worker publica a AVIF, a URL
muda e o navegador busca a nova variante em vez de continuar usando o original
em cache.

## Consequências

- A API não espera pela conversão, e a fila sobrevive a reinícios do worker.
- Os paths de mídia variam por versão e retornam ETag para revalidação de cache.
- A URL versionada muda da variante `original` para `avif` ao concluir a fila;
  a interface acompanha o estado enquanto estiver `pending` ou `processing`.
- Transparência e proporção seguem as regras existentes do otimizador Pillow;
  não há upscale.
- Em produção, logos raster dependem do storage Drive configurado, assim como
  as imagens de produto. Sem credenciais Drive, o fallback de desenvolvimento
  é process-local e não sobrevive ao restart.
- O banco guarda somente IDs e estados; os bytes ficam no Drive.
