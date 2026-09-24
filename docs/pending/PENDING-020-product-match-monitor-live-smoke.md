# PENDING-020 — Product Match live smoke para monitores

- Status: IN_PROGRESS
- Tipo: TESTING
- Prioridade: P2
- Área: matching/monitor
- Origem: 2026-09-23 — Product Match de monitores por código do fabricante
- Atualizado: 2026-09-23

## Contexto

A regra de código de modelo para monitores foi implementada e validada com
testes unitários. Falta executar o Product Match integrado em mais de um
produto real de monitor existente no projeto, cobrindo código igual, divergente
e omitido entre lojas.

## Feito

- Identificação genérica de códigos de monitor e comparação completa/exata.
- Fallback quando o código não está disponível, com atributos técnicos de tela.
- Testes unitários cobrindo formatos de fabricantes, sufixo, código ausente e
  decisão conflitante.
- MatchingEngine validado com o título PDP real salvo de `Gigabyte GS24F14`.

## Falta

- Executar `ProductMatchService` / MatchRun ponta a ponta em dois ou mais
  monitores reais cadastrados no ambiente, cobrindo código igual, código
  divergente, código ausente em um lado e ausência nos dois lados.
- Registrar resultados e confirmar que candidatos sem código não são rejeitados
  pela regra nova.

## Por que não terminou

- O repositório contém apenas um PDP de monitor salvo (`data/_terabyte_live.html`)
  e não há API, frontend ou worker escutando nas portas locais verificadas.
- O daemon Docker local negou acesso ao pipe `docker_engine`, então não foi
  possível iniciar o ambiente oficial para rodar MatchRun integrado.

## Impacto

A implementação está coberta por testes de parser e matcher, mas a validação
integrada com vários produtos reais e lojas ainda não foi realizada.

## Relacionado

- `src/scout_api/modules/crawler/utils/category_profiles/extra_parsers.py`
- `src/scout_api/modules/matching/identity.py`
- `src/scout_api/modules/matching/engine.py`
- `tests/unit/test_matching_regression.py`
- `data/_terabyte_live.html`
- `docs/crawler/product-identity.md`

## Pronto quando

- Product Match integrado executado em pelo menos dois monitores reais.
- Resultados registrados para códigos iguais, diferentes e ausentes; ausência
  de código segue para a cascata normal sem rejeição automática pelo novo sinal.
- Sem aumento de falsos positivos entre modelos semelhantes.
