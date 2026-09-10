# ADR-0007: Centralizar configuração em variáveis de ambiente

- Status: Accepted
- Data: 2026-09-10

## Contexto

Porta, ambiente e debug variam entre desenvolvimento, CI e produção.

## Problema / decisão necessária

Como configurar sem espalhar leituras de ambiente ou versionar secrets?

## Alternativas consideradas

`os.getenv` em cada módulo; classe central com `pydantic-settings`.

## Decisão

Centralizar em `core/config.py`, usando `pydantic-settings` e `.env` ignorado.

## Justificativa

Defaults, validação e origem da configuração ficam em um único ponto tipado.

## Consequências positivas

Contrato explícito e fácil adaptação entre ambientes.

## Trade-offs / consequências negativas

Novas variáveis exigem sincronização de documentação e Compose.
