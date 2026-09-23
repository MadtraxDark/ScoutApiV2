# ADR 0033: Progressive search from structured ProductIdentity (not raw PDP title)

- Status: aceito
- Data: 2026-09-22
- Relacionado: [0019](0019-product-matching.md), [0024](0024-product-match-evidence-cascade.md),
  [0026](0026-product-identity-brand-model-variant.md),
  [0027](0027-category-profile-product-identity.md)

## Contexto

Falsos `NO_MATCH` em Product Match ocorreram quando o título comercial longo da
PDP de referência (ex.: smartphone com câmeras, bateria, slogans “AI”) não
produzia uma **frase de série** para SERP. O identity compactava o modelo
(`galaxys25ultra`) corretamente, mas `model_search_phrase` só expandia iPhone /
GPU / SSD / console — não Galaxy. A ladder caía em `brand + storage`
(`samsung 256gb`) e o cap de SERPs vazias (`_MAX_EMPTY_SEARCH_QUERIES`) podia
encerrar a loja antes de qualquer query com o modelo comercial.

Pesquisa externa (entity resolution / catalog matching):

| Abordagem | Veredito ScoutApiV2 |
|---|---|
| Raw title similarity | Insuficiente sozinha (já ADR 0019/0024) |
| Normalized + structured attributes | **Adotar** (já parcial) |
| Blocking + detailed match | **Adotar** (SERP = blocking; matcher = detalhe) |
| Progressive / query relaxation | **Adotar e corrigir** (série comercial obrigatória) |
| Identifier-first (GTIN/MPN) | Já adotado; não inventar IDs |
| Splink / dedupe / Fellegi–Sunter | Excessivo agora (batch ER, não live SERP) |
| RapidFuzz / fuzzy title | Já parcial (`token_set_ratio`); só evidência secundária |
| Embeddings / vector DB / LLM | Rejeitado (variantes 256≠512 semanticamente próximas) |
| Elasticsearch próprio | Desnecessário — lojas já fornecem Search |

Fontes: Zarenk/product-matcher; catalog-forge (attribute roles; unknown≠conflict);
model-word blocking (Frasincar InfFus 2020); query relaxation / QNER ecommerce;
SO record-linkage / product title fuzzy matching; Kinyoubi “rapidfuzz enough
until blocking fails”.

## Problema / decisão

Como gerar queries de retrieval tolerantes sem enfraquecer o matcher rigoroso,
de forma genérica (não hardcode de SKU)?

## Decisão

1. **SEARCH tolerante / MATCH rigoroso** permanece: retrieval maximiza recall;
   `MatchingEngine` preserva precision (variante, sufixo de modelo, GTIN).
2. `model_search_phrase` emite série comercial **human-spaced** também para
   Galaxy S-series e expande tokens compactados (`galaxys25ultra` →
   `galaxy s25 ultra`; iPhone compacto idem). Para **placas-mãe**, emite
   família + board code + Wi-Fi (`tuf gaming b650m-e wifi`) e a ladder
   progressiva evita queries `brand` / `brand + wifi` nascidas de variant
   Wi-Fi misclassificada como cor.
3. Ladder progressiva continua: GTIN/MPN → brand+série+storage → série+storage
   → sinônimos de cor → brand+série → janela de título com stopwords de
   marketing (câmera/bateria/AI/celular), **sem** usar o título bruto inteiro
   como query primária. Suffixed board tokens (`B650M-E`) são compactados
   antes do stopword `e` apagar o discriminante.
4. Cores marketing compostas (`titânio preto` / `titanium black`) canonicam para
   a matiz base (`black`) para gates e sinônimos de SERP. Labels `WiFi` /
   `wireless` **não** entram no gate `color`.
5. Não introduzir Splink, Elasticsearch, vector DB, embeddings ou LLM nesta
   etapa. Não baixar thresholds do matcher para mascarar falha de retrieval.
6. Missing ≠ conflict permanece (ADR 0024). Contagem de slots de memória
   (`ram=4` unitless) não é gate de variante.
7. Quando a SERP omite o título do card (Magalu static HTML), usar
   `title_hint_from_url` no slug da PDP para ranking/prefilter — sem inventar
   atributos; o matcher continua baseado no scrape da PDP.

## Justificativa

A falha observada era de **candidate generation** (queries sem série), não de
threshold de score. A correção proporcional reutiliza abstrações existentes
(`ProductIdentity`, progressive queries, prefilter SERP, CategoryProfile para
detecção de categoria) sem nova infraestrutura.

## Consequências

- Melhor recall em smartphones (e qualquer família coberta por
  `model_search_phrase` / expansão compacta).
- Matcher continua rejeitando S25≠S25 Ultra, 256≠512, acessórios.
- SERP ainda depende da qualidade por loja; falha de search continua ERROR, não
  NO_MATCH silencioso.
- Novas famílias comerciais podem precisar de frase SERP explícita — preferir
  CategoryProfile / parsers de título a `if` espalhados.

## Relacionado

- `modules/matching/identity.py` (`build_search_queries`, `model_search_phrase`)
- `modules/matching/product_match_service.py` (progressive + empty-search cap)
- Testes: `tests/unit/test_matching_regression.py`
