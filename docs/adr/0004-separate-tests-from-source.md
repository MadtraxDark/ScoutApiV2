# ADR-0004: Manter testes fora de src

- Status: Accepted
- Data: 2026-09-10

## Contexto

Testes validam o runtime e não devem fazer parte do pacote de produção.

## Problema / decisão necessária

Onde organizar os testes?

## Alternativas consideradas

Testes dentro de `src`; diretório `tests` separado por tipo.

## Decisão

Manter testes em `tests/unit`, `tests/integration` e `tests/e2e`.

## Justificativa

Separa runtime de validação e explicita a abrangência dos testes.

## Consequências positivas

Pacote de produção mais claro e testes seletivos.

## Trade-offs / consequências negativas

A correspondência entre teste e módulo é convencional, não física.
