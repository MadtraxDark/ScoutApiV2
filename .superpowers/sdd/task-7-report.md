# Task 7 Report — Phase 7: Visão VIP S25 vs B650M A/B Root-Cause

**Data:** 2026-09-23  
**Status:** ✅ CONCLUÍDO — diagnóstico completo, gate cumprido

---

## Status

DONE — probe executado, veredicto escrito, gate de diagnóstico cumprido.

## Veredicto (uma linha)

**INCOMPLETE HYDRATION** — S25 Ultra (0/3 OK) carrega shell Next.js de 114 KB mas RSC nunca popula `/prod/` cards; B650M (3/3 OK) hidrata normalmente com 3 links; o marker `cf_challenge_platform` é script CF embutido no bundle (DOM 114 KB → não é interstitial; `is_challenge_page()` = False nas 3 iterações).

## Evidências-chave

| Métrica | S25 Ultra | B650M-E WIFI |
|---|---|---|
| Iterações OK | 0/3 | 3/3 |
| nav_result | `incomplete_hydrate` (3×) | `ok` (3×) |
| avg /prod/ links | 0.0 | 3.0 |
| avg DOM (KB) | 114.6 | 120.8 |
| avg duração (ms) | 3785 | 2543 |
| URL final | correta (sem redirect) | correta |
| `is_challenge_page()` | False (3×) | False (3×) |
| marker `cf_challenge_platform` | iter 1 apenas (script CF no bundle) | ausente |
| genuine_empty markers | ausentes | ausentes |

**Categoria descartada:** INFRA (B650M OK no mesmo container), WAF hard block (DOM 114 KB com URL correta), genuine empty (sem "nenhum resultado"), query slug errado (URL correta gerada).

**Causas prováveis (por probabilidade):**
1. SERP de smartphones tem RSC payload mais lento — settle_ms (5 s) insuficiente para essa categoria.
2. S25 Ultra não está no catálogo da Visão VIP (genuine empty sem marcador visível).
3. Throttling assimétrico Cloudflare por query de alta comercialidade (hipótese secundária).

## Concerns

- `cf_challenge_platform` apareceu em iter 1 do S25 (mas não em 2 e 3); pode ser variação de caching do bundle Next.js, não indica WAF assimétrico por si só.
- Sem evidência de "genuine empty" visual → causa 1 vs 2 ainda não distinguida; investigação de settle_ms maior ou HTTP/RSC endpoint pode separar os casos.
- Gate Task 9 cumprido: **não iniciar Strategy A sem este diagnóstico** — agora disponível.

## Arquivos

- Script: `scripts/probe_visaovip_serp_ab.py`
- Veredicto: `memory/working/2026-09-23-camoufox-visaovip-reliability.md` (seção `VISAO_VIP_DISCOVERY`)
- Próximo: Task 9 (Strategy A — settle_ms adaptativo ou fallback HTTP/RSC para S25)

## Pendências restantes

Nenhuma pendência nova criada nesta tarefa.  
Próximo trabalho: Task 9 (Strategy A) — apenas após leitura deste diagnóstico.
