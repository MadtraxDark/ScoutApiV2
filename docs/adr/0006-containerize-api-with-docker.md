# ADR-0006: Usar Docker como execução oficial

- Status: Accepted
- Data: 2026-09-10

## Contexto

A API precisa de execução reproduzível localmente, em CI/CD e em deploy.

## Problema / decisão necessária

Como padronizar o runtime sem depender do host?

## Alternativas consideradas

Python instalado no host; Dockerfile e Docker Compose.

## Decisão

Usar Docker como execução e hospedagem oficial, com `Dockerfile` e `compose.yaml`.

## Justificativa

Imagens fixam runtime e Compose mantém o fluxo local simples.

## Consequências positivas

Reprodutibilidade, healthcheck e usuário não-root no runtime.

## Trade-offs / consequências negativas

O fluxo oficial requer Docker disponível.
