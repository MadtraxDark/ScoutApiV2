# Product Identity & Attribute Normalization

Camada canônica de identidade de produto do ScoutApiV2 (ADR 0026 + ADR 0027).

## Princípios

| Conceito | Significado |
|---|---|
| `brand` | Fabricante / board partner |
| `model` | Identidade base pesquisável (chip, linha, SKU de CPU, …) |
| `variant` | Refinamento comercial opcional (cooler, cor+storage, Digital/Disc) |
| `attributes` | Características técnicas **presentes nas fontes** (nunca inventadas) |
| `product_line` | Linha interna opcional (TUF, ROG) — pode entrar na variant pública |

**Prioridade de fonte:** specifications → structured → selected model/variant →
title fallback → `null`.

**missing ≠ conflict:** atributo ausente de um lado não rejeita match.

**Não over-inferir:** `Ryzen 7 7800X3D` não ganha `cores=8` sem fonte.

## Arquitetura

```text
resolve_product_identity
  → detect_product_category (CategoryProfile registry)
  → specs / structured fill
  → CategoryProfile.parse_title (fallback brand/model)
  → CategoryProfile.extract_attributes (title → attrs críticos)
  → format_identity_variant
```

Código:

- `utils/category_profiles/` — `CategoryProfile`, registry, normalizers, parsers
- `utils/category_profiles/attribute_extractors.py` — extractors Phase 4–7
- `utils/product_identity.py` — grammars GPU/phone/CPU/RAM/SSD + chaves canônicas
- `utils/product_attributes.py` — prioridade de fonte + bundle

## Adicionar uma categoria

1. Registrar `CategoryProfile` em `category_profiles/definitions.py`
2. Needles de detecção + prioridade
3. `supported_attributes`, `critical_conflict_keys`, `search_filters`
4. `parse_title` (ou deixar `None` se só metadata)
5. `extract_attributes` em `attribute_extractors.py` (auto-wire por `id`) **ou**
   declarar `specs_only_critical` quando o atributo crítico só vem de specs
   (ex.: `mpn` em printer/scanner)
6. Testes em `tests/unit/test_category_profiles.py`
7. Atualizar esta doc se o contrato público mudar

Não editar o core do resolver com `if category == …` novos.

## Normalização comum

`128GB`→`128 GB`, `6000mhz`→`6000 MHz`, `DDR 5`→`DDR5`, `2 X 16 GB`→`2x16 GB`.
Não inventar kit a partir só do total (`32GB` ≠ `2x16`).

Aliases de marca só com evidência (`ASUSTeK`→`ASUS`).

## Search

`GET /products/search` — filtros opcionais e combináveis:

- `brand`, `model`, `variant`, `category`
- attrs: `vram`, `memory_type`, `capacity`, `frequency`, `chipset`, `socket`,
  `storage`, `refresh_rate`, `wattage`, `panel`

`variant` omitido = todas as implementações do modelo base.

## Match

Evidência forte: GTIN/MPN/model_number. Title similarity só complementar.
Conflitos críticos por profile (ex.: `rtx5070`≠`rtx5070ti`, Digital≠Disc).

## Persistência

- Tipado: `brand`, `model`, `variant_key`
- JSON `attributes`: `category` + attrs esparsos validados pelo profile
- Identifiers: tabela `product_identifiers` (GTIN)

Promover atributo quente a coluna/índice só com evidência de filtro frequente.
**Hoje:** filtro `category` + attrs roda em memória sobre JSON após prefilter de
`brand` — volume atual **não** justifica coluna `category` indexada nem GIN em
attrs (reavaliar quando search multi-attr for caminho quente em produção).

## Profiles registrados

Ver `category_profiles/definitions.py` (GPU, RAM, MB, CPU, phone, tablet, SSD,
notebook, PSU, cooler, fan, monitor, TV, console, peripherals, network,
printer/scanner/webcam, audio, camera/lens, NAS/UPS/chargers/docks/cables,
furniture, accessory).

Maturidade:

- Phase 1–3: grammars de título fortes (GPU/RAM/MB/CPU/phone/SSD/console/…).
- Phase 4–7: `extract_attributes` cobre `critical_conflict_keys` extraíveis do
  título (pack_count, port_count, vesa, bay_count, connectors, …).
- Printer/scanner: `mpn` é **specs-only** (`specs_only_critical`) — título não
  inventa identificador.
