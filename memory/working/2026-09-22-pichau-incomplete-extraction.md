# Pichau spider — investigação Ryzen 5800X3D (2026-09-22)

## Objetivo

Corrigir extração incompleta do spider Pichau (offer + details + specs +
pricing) sem hardcode do produto de regressão.

## Baseline live (`POST /crawl`) — ANTES

| Campo | Valor |
|---|---|
| price | 2517.64 (`json-ld`) |
| pix_price | null |
| original_price | null |
| installments | null |
| product_id / sku | slug MPN em ambos |
| brand / model | AMD / Ryzen 7 5800X3D (título) |
| specifications | ausentes |
| duração | ~22s (Camoufox) |

## Causa raiz

HTML Next.js embute Magento `product` em `self.__next_f.push` com aspas
escapadas. Regex antigo exigia `"product":` literal → 0 matches → fallback
JSON-LD (só cartão).

## Correção

1. Decode flight (padrão Visão VIP) + brace-scan
2. Pricing: `price=final_price`, `pix=avista`, `original=base_price`
3. Specs Magento + identidade
4. HTTP-first `curl_cffi` (`PichauHttpFirstHtmlFetcher`)
5. SERP via `url_key` no flight

## DEPOIS (`POST /crawl`, include_images=true)

| Campo | Valor | Fonte |
|---|---|---|
| title | Processador AMD Ryzen 7 5800X3D… | rsc |
| brand | AMD | marcas_info |
| model | Ryzen 7 5800X3D | title identity |
| product_id | 66151 | Magento id |
| sku / MPN | 100-100000651POF | Magento sku |
| price | 2517.64 | final_price |
| pix_price | 2139.99 | avista |
| original_price | 3294.11 | base_price |
| installments | 12 × 209.80 | max/min installment |
| images | 3 | media_gallery |
| parse_quality | rsc-complete | |
| total_ms | **863** | http-direct |

## Multi-produto (HTTP curl_cffi)

- GPU / MB / RAM / monitor via SERP `url_key`: todos `rsc-complete`
