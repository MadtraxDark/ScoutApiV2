# ADR 0026: Identidade canônica brand / model / variant

- Status: Accepted
- Data: 2026-09-20

## Contexto

O fallback de título em `resolve_product_identity` era sequencial: após
prefixos de categoria, o primeiro token virava `brand` e os seguintes
`model` até um stop token. Títulos SEO de GPU
(`Placa De Vídeo GPU 12GB Dual Asus GeForce RTX 5070 OC Edition`)
preenchiam `brand` (estruturado ou primeiro token útil) mas paravam em
`12GB` / `Dual`, deixando `model=null` e `variant=null`. O chip ia para
`gpu_model`, não para o `model` público.

O Product Match já distinguia chip (`rtx5070` ≠ `rtx5070ti`) de cooler
(`Shadow 3X` ≠ `Gaming Trio`), mas o scrape público e o catálogo não
exponham essa separação de forma pesquisável.

Pesquisa (OSS `revizor` / ProductTagger, `catalog-forge`,
`product-matcher` / factorypure, SO title parsing, Reddit NER de
títulos): structured-first; parsers por categoria (gazetteer + padrões
de família, não SKU); título como fallback; atributo ausente ≠ conflito;
NER/LLM só se regras falharem. Descartado LLM/embeddings no momento.

## Problema / decisão necessária

Como preencher `brand` / `model` / `variant` de forma genérica (GPU,
smartphone, CPU, RAM, SSD) para busca ampla por modelo base e busca
restrita por variante, sem hardcode de produto e sem sobrescrever
dado estruturado confiável?

## Alternativas consideradas

- **Regex global único** — tokens mudam de significado por categoria
  (`OC Edition` vs `128GB`).
- **Dicionário de SKUs** (`if "RTX 5070"`) — frágil e não reutilizável.
- **NER/LLM** — overkill; a pesquisa recomenda regras + padrões de
  família primeiro.
- **Parsers registrados por categoria + chaves canônicas** — extensível
  e determinístico.

## Decisão

1. `model` = identidade base pesquisável (chip GPU, trim de telefone,
   SKU de CPU, linha de RAM/SSD). Sufixos críticos (`Ti`, `Super`,
   `XT`/`XTX`, `Pro`, `Max`, `X3D`) pertencem ao modelo.
2. `variant` = refinamento comercial opcional (cooler Dual/TUF/Shadow,
   ou dimensões `color`/`storage` nas demais categorias). `null` quando
   não houver linha comercial clara (`OC Edition` sozinho não basta).
3. Parsers por categoria em `utils/product_identity.py`, acionados
   depois da prioridade global: specs → structured → title → null.
   Structured que já é modelo base só é canonicalizado. Cooler/MPN
   estruturado é reclassificado só quando o parser extrai um modelo
   base do título.
4. Canonicalização: `Geforce RTX5070` / `NVIDIA GeForce RTX 5070` →
   display `GeForce RTX 5070`, chave `rtx5070`. MPN
   (`DUAL-RTX5070-O12G`) não é equivalente automático a `Dual OC`.
   Marca de GPU usa gazetteer de *board partners* (fabricantes), não lista
   de SKU; `GeForce`/`NVIDIA` no título nunca vira `brand` quando existe
   um parceiro (ex. MSI depois do chip).
5. `GET /products/search?brand=&model=&variant=` — `variant` opcional.
   Sem variant, todas as implementações do modelo; com variant, restringe.
6. Product Match: `variant`/`edition` ausente continua **não** sendo
   conflito; divergência explícita Dual ≠ Gaming Trio rejeita.

## Justificativa

Atende busca ampla (`ASUS` + `GeForce RTX 5070`) e específica
(`variant=Dual OC Edition`) com a mesma extração usada no scrape,
sem ML pago e sem dicionário de produto.

## Consequências positivas

- Títulos SEO de AIB (ASUS/MSI/Gigabyte) preenchem chip + cooler.
- `RTX 5070` ≠ `RTX 5070 Ti` na busca e no match.
- Categorias extras entram como parser registrado, não como `if` de SKU.

## Trade-offs / consequências negativas

- Linhas de cooler novas demais, sem âncora léxica, ficam `variant=null`
  (preferível a falso positivo).
- Display canônico `GeForce RTX …` altera `model` antes literal
  (`RTX 5060 Ti` → `GeForce RTX 5060 Ti`) nas lojas que só publicavam
  o chip curto.
- SERP/match de GPU deve parsear **o título**, não o blob
  `model_compacto + title` (senão a marca vaza para `edition`).

## Relacionado

- ADR 0019, ADR 0024
- `docs/crawler/contracts.md`
- `utils/product_identity.py`, `utils/product_attributes.py`
- `GET /products/search`
