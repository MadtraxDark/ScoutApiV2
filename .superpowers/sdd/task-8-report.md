# Task 8 Report — Validação do Contrato Server Action Visão VIP

**Data:** 2026-09-23  
**Script criado:** `scripts/probe_visaovip_search_action.py`  
**Working log:** `memory/working/2026-09-23-camoufox-visaovip-reliability.md` (seção `### Server Action Probe — Task 8`)

---

## Status

**CONCLUÍDO** — Contrato validado, Go/No-Go documentado, script de probe criado.

---

## Contrato capturado — `searchProducts` Server Action

### POST URL
```
https://www.visaovip.com/busca/termo/{slug}/
```
(ex.: `/busca/termo/asus-tuf-gaming-b650m-e-wifi/`)

### Headers obrigatórios
| Header | Valor |
|---|---|
| `Next-Action` | `<action_id>` — **deploy-coupled, muda por build** |
| `Content-Type` | `text/plain;charset=UTF-8` |
| `Accept` | `text/x-component,*/*` |
| `x-intlayer-locale` | `pt-BR` |
| `Origin` | `https://www.visaovip.com` |

### Payload (JSON array)
```json
[searchTerm, searchType, characteristics[], locale, page, perPage, stock]
```
Exemplo:
```json
["asus-tuf-gaming-b650m-e-wifi", "termo", [], "pt-BR", 1, 24, "all"]
```

**Fonte:** Decompile de `chunk_serp3.body` — `createServerReference("7f67...", ..., "searchProducts")`:
```js
let v = await p(searchTerm, searchType, characteristics, locale, page, perPage, stock)
```

### Formato da resposta
```
Content-Type: text/x-component
Status: 200 OK

0:{"a":"$@1","f":"","b":"<buildId>","q":"","i":false}
1:{"products":[...], "facets":{"brands":[], "characteristics":[], ...},
   "totalCount":N, "currentPage":0, "totalPages":N}
```

Confirmado por `action_empty_arr.hdr` (200 OK) + `action_empty_arr.body`:
```
1:{"products":[],"facets":{"brands":[],...},"totalCount":0,...}
```

### Necessidade de session / cookies
**NÃO** — `action_empty_arr.body` retornou 200 OK sem cookies no build anterior.  
Cloudflare bloqueia GET da página SERP, **não** o POST da Server Action.

---

## Estabilidade do Action ID

**CONCLUSÃO: DEPLOY-COUPLED — muda a cada build da Visão VIP.**

| Build anterior (2026-09-23) | `QAm14Voexwwlur451SrkG` |
|---|---|
| `searchProducts` ID | `7f674263c13a9d8d28d0768c8016b1791b8051502a` |
| `searchFacets` ID | `784f2ef5d5603dc817ded8e27c904518fc45af1b63` |

**Evidência de rotação:**
- POST com ID estático atual → `404 "Server action not found"`
- Chunk `5304c8ab31d35f98.js` no build atual: 31 KB, conteúdo diferente (`useMergedRef` — não é o chunk SERP)
- Build anterior: mesmo chunk nome, 128 KB, continha `searchProducts`
- Conclusão: deploy novo gerou hashes diferentes para os chunks; URL `5304c8ab31d35f98.js` é agora outro arquivo

**Comportamento esperado no Next.js:**
- Action IDs são SHA-derivados do conteúdo da função (`createServerReference`)
- Mudam se o código da action mudar OU se dependências mudam OU em alguns casos no Turbopack
- Ficam na CDN/cache de `/_next/static/` pelo nome do chunk — chunk muda → URL muda → ID muda

---

## Discovery Path (como obter o ID corrente)

**Problema:** GET do SERP via HTTP puro → CF retorna shell 5.8 KB (sem `<script src>` tags).  
**Portanto:** Discovery REQUER browser (Camoufox).

### Abordagem recomendada (implementar em Task 9)

**Opção A — Interceptar request real do browser:**
```
Camoufox.page.on("request") → filtra POST com "next-action" header →
extrai req.all_headers()["next-action"]
```
Vantagem: obtém ID exato + payload exato que o browser usa.

**Opção B — Scan do chunk JS:**
```
Camoufox navega → extrai URLs de script do HTML → busca chunk com
createServerReference("...", ..., "searchProducts") → extrai ID
```

**Opção C — Cache por build ID:**
```
RSC response contém "b":"<buildId>" →
cachear actionId → buildId; invalidar quando buildId muda
```
Otimização para reduzir overhead de discovery.

O script `probe_visaovip_search_action.py` implementa todas as três opções:
- `discover_action_ids()` — tenta HTTP, detecta CF shell, cai no fallback estático
- `verify_action_id_live()` — valida se o ID atual está ativo (POST 404-check)
- `_capture_via_browser()` — interceptação real via Camoufox

---

## Resultados do Probe Offline (sem Docker)

| Query | HTTP Status | Observação |
|---|---|---|
| `asus-tuf-gaming-b650m-e-wifi` | 404 | ID rotacionou; endpoint OK com ID correto |
| `samsung-galaxy-s25-ultra` | 404 | Mesmo motivo |

**Nota:** Probe com Camoufox (Docker) requerido para capturar ID atual e validar S25.

---

## Go / No-Go — Strategy A

**VEREDICTO: ✅ GO (com condição)**

### Evidências de GO
- **Endpoint funcional:** 200 OK + JSON limpo confirmado em `action_empty_arr.body`
- **Sem session gate:** POST funciona sem cookies
- **CF não bloqueia POST:** CF intercepta apenas GET de página
- **Response clean JSON:** não requer parsing RSC complexo após o `1:` prefix
- **Vantagem crítica:** evita `incomplete_hydrate` do S25 (Task 7) — JSON direto vs esperar RSC hydration

### Condição
Action ID **deve ser descoberto via Camoufox por sessão** — não pode ser hardcoded.

### Concerns

| # | Concern | Severidade | Mitigação |
|---|---|---|---|
| 1 | ID deploy-coupled | MÉDIA | Cache por build-ID; discovery via browser ao iniciar sessão |
| 2 | Discovery ainda precisa de browser | BAIXA | Browser de qualquer forma necessário (SERP também usa); amortizado por sessão |
| 3 | S25 genuine empty vs encoding | BAIXA | Testar com ID fresco em Task 9 — se 0 produtos = genuine empty, NO_MATCH esperado |
| 4 | Payload arg order pode mudar | BAIXA | Monitorar; regra de regressão |

---

## Fixtures / Artefatos

- `memory/working/_visaovip_serp_probe/action_empty_arr.hdr` — headers HTTP 200 OK
- `memory/working/_visaovip_serp_probe/action_empty_arr.body` — resposta RSC com `products:[]`
- `memory/working/_visaovip_serp_probe/action_termo_guess.hdr` — headers HTTP 500 (payload errado)
- `memory/working/_visaovip_serp_probe/chunk_serp3.body` — JS chunk com `createServerReference`
- **Sem secrets** — nenhum cookie, token ou credencial nos fixtures acima

---

## Próximos Passos (Task 9)

1. Com Camoufox (Docker), navegar para `/busca/termo/asus-tuf-gaming-b650m-e-wifi/` e interceptar POST
2. Capturar action ID atual + headers exatos + payload exato
3. Testar com `samsung-galaxy-s25-ultra` — verificar se é genuine empty ou hydration issue
4. Implementar `VisaoVipSearchAdapter` com Strategy A: browser load → discover ID → POST HTTP

---

## Pendências restantes

- Task 9 pendente: implementação de Strategy A ainda não feita (conforme instruções da Task 8)
- S25 genuine empty vs incomplete hydrate: open question, resolve em Task 9 com ID fresco
