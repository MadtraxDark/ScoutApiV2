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
| `PERFORMANCE` | Lentidão recorrente / regressão de tempo não resolvida |

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
| [PENDING-012](PENDING-012-mercadolivre-serp-account-verification.md) | Mercado Livre SERP account-verification (auth wall) | OPEN | INCOMPLETE | P1 | crawler/mercadolivre |
| [PENDING-014](PENDING-014-promo-timer-spider-wiring.md) | Extrair timers de promo em spiders live (Pichau/ML/Shopee) | OPEN | INCOMPLETE | P2 | crawler/promotions |

*(pendências ativas: 2)*

Resolvida em 2026-09-21:

- PENDING-013 PriceScout galeria FE + smoke Drive real — arquivo apagado;
  OAuth Drive no `.env`, container API recriado, smoke
  `scripts/smoke_google_drive_images.py` OK; import com `images[]` +
  `display_url` no FE (`/admin/produtos/{id}`)

Resolvida em 2026-09-20:

- PENDING-011 Extratores profundos CategoryProfile Phase 5–7 — arquivo apagado;
  `attribute_extractors` + `specs_only_critical` (printer/scanner mpn) +
  benchmark unitário; índices SQL adiados por volume (ADR 0027)

Resolvida em 2026-09-19:

- PENDING-010 Validação live Mercado Livre (Docker + curl_cffi) — arquivo
  apagado; live `/crawl*` + `/match` multi-loja OK (ADR 0025)

## Resolvidas

Arquivo apagado (preferencial) ou pasta [`resolved/`](resolved/) quando arquivado.
O Git preserva o histórico em qualquer caso.

Resolvidas em 2026-09-19 (Best Buy Akamai):

- [`resolved/PENDING-009-bestbuy-us-proxy-intermittent.md`](resolved/PENDING-009-bestbuy-us-proxy-intermittent.md)
  — warmup homepage + sticky US sessid + retry `NET_RESET`; scrape live OK

Resolvidas em 2026-09-14 (SERP matching PENDING-008):

- PENDING-008 Shopping China `/quick_search` HTTP + Nissei `/py/catalogsearch`
  + Shopee `search_items` intercept (limitação de sessão fria documentada em
  `docs/crawler/stores/shopee.md`) — arquivo apagado

Resolvidas em 2026-09-14 (product matching search):

- PENDING-007 Search adapters matching para Amazon US, Shopee, Best Buy,
  Nissei, Shopping China (apagado)

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
