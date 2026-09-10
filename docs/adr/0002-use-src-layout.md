# ADR-0002: Usar src layout

- Status: Accepted
- Data: 2026-09-10

## Contexto

O pacote instalável deve ser separado dos arquivos de desenvolvimento.

## Problema / decisão necessária

Onde deve ficar o código da aplicação?

## Alternativas consideradas

Pacote na raiz; pacote dentro de `src/`.

## Decisão

Usar `src/scout_api` e configurar o empacotamento por setuptools.

## Justificativa

Reduz imports acidentais e aproxima testes do comportamento instalado.

## Consequências positivas

Pacote e código de desenvolvimento ficam claramente separados.

## Trade-offs / consequências negativas

Execução local exige instalação editável ou `--app-dir src`.
