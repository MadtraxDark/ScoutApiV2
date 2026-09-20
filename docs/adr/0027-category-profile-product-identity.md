# ADR 0027: CategoryProfile registry for product identity

- Status: Accepted
- Data: 2026-09-20
- Supersedes (parcial): estende [0026](0026-product-identity-brand-model-variant.md)

## Contexto

ADR 0026 introduziu brand / model / variant e parsers por categoria para GPU
e algumas famílias. Expandir para dezenas de categorias de informática e
eletrônicos sem um contrato declarativo tende a virar `if/elif` e regex
acoplados no resolver.

Pesquisa (OSS `revizor` ProductTagger, Leipzig product-offer ER, MDM
catalog/taxonomy/attribute-schema, hybrid relational+JSONB):

- structured-first + title fallback conservador;
- schema de atributos **por categoria** (não coluna SQL por atributo);
- missing ≠ conflict (record linkage MAR);
- identidade tipada (brand/model) + atributos esparsos em JSON governado;
- NER/LLM só depois de falhar o determinístico.

## Decisão

1. Introduzir `CategoryProfile` + registry em
   `utils/category_profiles/`: cada categoria declara needles de detecção,
   atributos suportados, conflitos críticos, filtros de busca, aliases de
   marca e parser de título opcional.
2. O resolver único (`resolve_product_identity` / `parse_title_identity`)
   despacha pelo registry — adicionar categoria ≈ registrar profile + testes.
3. Persistência: manter `brand` / `model` / `variant_key` tipados;
   `attributes` JSON (já existente) guarda `category` e attrs esparsos.
   Não criar uma coluna por atributo agora; filtros quentes podem virar
   colunas/índices depois com evidência de query.
4. `GET /products/search` aceita `category` e filtros de atributo opcionais
   (`vram`, `memory_type`, `capacity`, …) além de brand/model/variant.
5. Product Match continua precision-first; profiles documentam
   `critical_conflict_keys` / `strong_match_keys` (GPU edition missing ≠
   conflict permanece).
6. Sem LLM/embeddings nesta etapa.

## Alternativas rejeitadas

- Regex global único.
- NER/LLM como caminho primário.
- EAV puro ou JSONB para identidade core.
- Endpoints de search separados por categoria.

## Consequências

- Extensão previsível (Phase 1–7 profiles registrados).
- Extratores de atributos de título (`attribute_extractors.py`) cobrem chaves
  críticas Phase 4–7; atributos só de specs usam `specs_only_critical`.
- Detecção notebook vs GPU exige regras de desempate (chassis / HX+RTX).
- Índices SQL para `category`/attrs ficam para quando o volume de search
  justificar (hoje JSON + filtro em memória após brand).

## Relacionado

- ADR 0026, 0019, 0024
- `docs/crawler/product-identity.md`
- `docs/crawler/contracts.md`
