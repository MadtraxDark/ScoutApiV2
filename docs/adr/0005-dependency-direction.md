# ADR-0005: Direcionar dependências da camada HTTP para infraestrutura

- Status: Accepted
- Data: 2026-09-10

## Contexto

Regras de negócio devem permanecer independentes do framework HTTP e do armazenamento.

## Problema / decisão necessária

Como evitar acoplamento e dependências circulares?

## Alternativas consideradas

Imports livres; direção `router -> service -> repository -> database`.

## Decisão

Adotar `HTTP -> router -> service -> repository -> database`.

## Justificativa

Essa direção torna regras testáveis e reduz acoplamento ao FastAPI.

## Consequências positivas

Testes unitários podem evitar framework e infraestrutura.

## Trade-offs / consequências negativas

Módulos maiores exigirão tradução explícita de modelos e erros.
