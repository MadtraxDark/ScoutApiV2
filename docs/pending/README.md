# Pendências — ScoutApiV2

Rastreador canônico de trabalho **acionável** incompleto, bloqueios e lacunas
que precisam sobreviver entre sessões.

Limitações de produto/loja **aceitas como estão** ficam em
`docs/crawler/stores/` (“Known limitations”), não aqui.

Regras do agente: [`.cursor/rules/pending-work.mdc`](../../.cursor/rules/pending-work.mdc),
[`.cursor/rules/task-completion.mdc`](../../.cursor/rules/task-completion.mdc),
[`.cursor/rules/research-and-problem-solving.mdc`](../../.cursor/rules/research-and-problem-solving.mdc).

## Regra de conclusão

A tarefa só está completa quando os critérios relevantes forem atendidos.
Caso contrário: concluir o trabalho **ou** criar/atualizar um `PENDING-NNN`
**na mesma tarefa**.

## Lifecycle (status)

| Status | Aparece no índice ativo? | Significado |
|---|---|---|
| `OPEN` | Sim | Aberto |
| `IN_PROGRESS` | Sim | Em andamento |
| `BLOCKED` | Sim | Bloqueado por fator externo **após** investigação técnica |
| `RESOLVED` | **Não** | Concluído — sai da lista ativa |

Antes de `BLOCKED` / “sem solução”: cumprir
[`.cursor/rules/research-and-problem-solving.mdc`](../../.cursor/rules/research-and-problem-solving.mdc)
e preencher a seção **Investigação** do [`template.md`](template.md)
(pesquisas, testes, descartes, referências). Assim a próxima sessão não
reinicia do zero.

## Tipo

| Tipo | Significado |
|---|---|
| `INCOMPLETE` | Funcionalidade parcial |
| `BUG` | Comportamento incorreto conhecido |
| `TESTING` | Código existe; falta validação/teste importante |
| `TECH_DEBT` | Funciona, mas há dívida relevante |
| `RESEARCH` | Precisa investigação antes de decidir |
| `DOCS` | Falta documentação importante |

## Prioridade

| Prioridade | Significado |
|---|---|
| `P0` | Crítico — correção/segurança/integridade |
| `P1` | Alto — lacuna grave ou caminho principal instável |
| `P2` | Médio — importante, há contorno |
| `P3` | Baixo — polish / dívida menor |

Não invente outro esquema de prioridade.

## Criar

1. Copiar [`template.md`](template.md).
2. Nomear `PENDING-NNN-slug.md` com o próximo número livre.
3. Incluir linha no **índice ativo**.
4. Linkar store/ADR quando útil.
5. Nunca gravar secrets/cookies/tokens.

## Atualizar (parcial)

Atualize seções Done / Missing / Done when. Remova do Missing o que já terminou.
Mantenha a pendência aberta só com o que ainda falta.

## Resolver (completo)

1. Confirmar critérios “Done when”.
2. Remover do índice ativo.
3. **Padrão:** apagar o arquivo (histórico no Git).
4. **Opcional:** mover para [`resolved/`](resolved/) se as notas de resolução
   forem úteis.
5. Limpar TODOs/`FIXME` e referências órfãs.

Itens resolvidos **não** ficam no índice ativo.

## Índice ativo

| ID | Título | Status | Tipo | Prioridade | Área |
|---|---|---|---|---|---|

*(nenhuma pendência ativa)*

## Resolvidas

Arquivo apagado (preferencial) ou pasta [`resolved/`](resolved/) quando arquivado.
O Git preserva o histórico em qualquer caso.

Arquivadas nesta linha de trabalho Amazon / CAPTCHA / auth:

- [`resolved/PENDING-001-amazon-live-validation-blocked.md`](resolved/PENDING-001-amazon-live-validation-blocked.md)
- [`resolved/PENDING-002-amazon-br-live-access-reliability.md`](resolved/PENDING-002-amazon-br-live-access-reliability.md)
- [`resolved/PENDING-003-captcha-challenge-resolution.md`](resolved/PENDING-003-captcha-challenge-resolution.md)

Resolvidas em 2026-09-14 (browser-use + parse):

- PENDING-004 Best Buy Apollo SSR `customerPrice` (apagado)
- PENDING-005 Magalu soft-404 `Oops!` → `ParseError` claro (apagado).
  Nota: o Oops do caso `/p/240590700/` era **produto/URL inválida**, não
  falha da integração Magalu; PDP válida (ex. `/p/jjhd6g4f9d/…`) scrapeia OK.
  Em validação live, trocar de URL antes de acusar regressão de loja.
- PENDING-006 Amazon BR `#qualifiedBuybox` / Pix à vista (apagado)
