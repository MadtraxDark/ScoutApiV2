# ADR-0003: Organizar código por feature

- Status: Accepted
- Data: 2026-09-10

## Contexto

Features evoluem em conjunto e precisam manter seus componentes próximos.

## Problema / decisão necessária

Como evitar diretórios globais que espalhem cada domínio?

## Alternativas consideradas

Diretórios globais de camadas; diretórios por feature.

## Decisão

Organizar funcionalidades em `modules/<feature>/`, criando partes internas somente quando necessário.

## Justificativa

Proximidade aumenta coesão sem exigir camadas artificiais.

## Consequências positivas

Features são fáceis de localizar e testar.

## Trade-offs / consequências negativas

Componentes compartilhados exigem decisão explícita sobre seu local.
