# ADR-0001: Usar modular monolith

- Status: Accepted
- Data: 2026-09-10

## Contexto

Projeto novo sem necessidade de implantação independente por domínio.

## Problema / decisão necessária

Como permitir evolução por domínio sem complexidade operacional prematura?

## Alternativas consideradas

Microservices desde o início; monólito sem módulos; modular monolith.

## Decisão

Adotar modular monolith com features em `src/scout_api/modules/`.

## Justificativa

Mantém implantação simples e preserva fronteiras de domínio visíveis.

## Consequências positivas

Uma implantação simples e possibilidade de extração futura.

## Trade-offs / consequências negativas

Módulos compartilham processo e exigem disciplina contra acoplamento.
