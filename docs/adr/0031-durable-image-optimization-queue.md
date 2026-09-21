# ADR 0031: Fila durável PostgreSQL para otimização AVIF

- Status: Accepted
- Data: 2026-09-21
- Relacionado: [ADR 0029](0029-google-drive-product-images.md)

## Contexto

ADR 0029 definiu original no Drive + AVIF assíncrono. A primeira
implementação usava `ThreadPoolExecutor` fire-and-forget no request de
cadastro. Isso tinha dois problemas:

1. O job podia iniciar **antes do commit** da request e não ver a linha.
2. Em restart da API, `optimized_status=pending` ficava órfão sem recovery.

O cadastro também não podia depender de AVIF: original ready já torna a
imagem utilizável (`display_url` → original).

## Problema / decisão necessária

Como executar AVIF em background com recovery após restart, sem Celery/
Redis extra, sem bloquear `POST /products`, e sem conversão duplicada entre
réplicas?

## Alternativas consideradas

- **Só `BackgroundTasks` / thread pool:** simples, mas perde jobs no restart
  (trade-off já anotado no ADR 0029).
- **Celery + Redis:** infra adicional; Redis no projeto é cache (ADR 0020),
  não SoT de fila.
- **Tabela `image_optimization_jobs` separada:** válida, mas duplica estado
  já modelado em `product_images.optimized_status`.

## Decisão

1. **Salvar produto ≠ converter AVIF.** O request persiste produto + original
   + metadata com `optimized_status=pending` e retorna sucesso.
2. Job durável vive na própria linha `product_images` (lease/claim:
   `optimization_attempts`, `optimization_next_attempt_at`,
   `optimization_claimed_at`, `optimization_claim_expires_at`,
   `optimization_worker_id`) — mesmo padrão do monitor (ADR 0030).
3. Worker/poller com `FOR UPDATE SKIP LOCKED` (PostgreSQL) + claim portátil
   (SQLite testes).
4. Execução: poller in-process no lifespan da API **e** serviço Compose
   `image-optimizer` (`python -m scout_api.modules.images.worker`).
5. Concorrência limitada por `IMAGE_AVIF_MAX_CONCURRENCY` (alias
   `IMAGE_OPTIMIZATION_CONCURRENCY`).
6. Entrega: `display_url` / `primary_image_url` preferem AVIF só quando
   `ready`; URLs com `?variant=original|optimized` (imutáveis por arquivo).

## Justificativa

Reutiliza PostgreSQL + padrão de claim já aceito no monitoramento. Proporcional
ao volume de imagens; recovery explícito; save path mensurável sem
`avif_conversion_ms`.

## Consequências positivas

- Cadastro não espera AVIF.
- Pending/processing/failed → frontend usa original.
- Restart retoma jobs.
- Duas réplicas não convertem a mesma imagem (lease).

## Trade-offs / consequências negativas

- Latência de até ~sweep interval até o AVIF iniciar (configurável; default 2s).
- Polling periódico no Postgres (aceitável no volume atual).
