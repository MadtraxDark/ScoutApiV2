# ADR 0025: Mercado Livre HTTP-first with TLS impersonation

- Status: Accepted
- Data: 2026-09-19

## Contexto

Mercado Livre (BR) bloqueia clientes HTTP “clássicos” (`urllib` / `requests`) no
handshake TLS (JA3/JA4). Mesmo com headers corretos, a API pública
`api.mercadolibre.com` e o HTML da PDP frequentemente respondem 403 ou um
interstício **Snoopy** (PoW + botão Continuar) com HTTP 200 e meta/title do
produto — sem JSON-LD de oferta.

Evidência local (2026-09-19):

1. `urllib` → 403 na API de items.
2. `curl_cffi` (`impersonate=chrome`) → HTTP 200 no PDP URL, mas corpo =
   challenge Snoopy (~14 KB, `verifyChallenge` / `#continue-button`).
3. Camoufox com wait pelo fim do PoW (e Continuar quando necessário) → PDP
   completa (~1 MB) com JSON-LD `Product` + `.ui-pdp-price`.
4. Comunidade (r/webscraping, guias 2025–2026): HTTP leve + fingerprint
   browser-like primeiro; browser só quando o HTML inicial não traz dados;
   preferir payload embutido (JSON-LD) a DOM pesado.

ADR 0016 rejeitou `curl_cffi` **sem pedido explícito**. Este ADR registra a
adoção **sob pedido explícito** para Mercado Livre, sem generalizar a todas as
lojas.

## Problema / decisão necessária

Como coletar oferta ML de forma resiliente, alinhada a Proxy Cost Mode, sem
parsear challenge como produto e sem introduzir Playwright paralelo?

## Alternativas consideradas

- **A — Só Camoufox + proxy FALLBACK:** funciona, mas sempre paga o custo de
  browser; HTTP impersonado às vezes basta após sessão aquecida.
- **B — Só API oficial Mercado Libre:** exige app/OAuth; muitos IPs recebem
  403 PolicyAgent; fora do caminho HTML do crawler.
- **C — Playwright + stealth plugin:** duplica o stack; o projeto já tem
  Camoufox (ADR 0009) com humanize e resolução de challenge (ADR 0017).
- **D — curl_cffi HTTP-first → Camoufox (direct → proxy FALLBACK); parse
  JSON-LD/DOM; resolver Snoopy no browser.**
- **E — curl_cffi para todas as lojas:** escopo amplo sem necessidade; Amazon
  já usa urllib HTTP-first (ADR 0016).

## Decisão

Adotar **D** apenas para hosts Mercado Livre BR:

1. `CurlCffiHtmlFetcher` — TLS/HTTP2 impersonation (`impersonate=chrome`),
   retries com backoff exponencial + jitter.
2. `MercadoLivreHttpFirstHtmlFetcher` envolve o fetcher compartilhado:
   **curl_cffi → Camoufox (StoreAware FALLBACK)** quando challenge, auth wall,
   não-PDP ou ausência de sinal de preço.
3. Detecção Snoopy em `is_mercadolivre_snoopy_challenge` / `is_challenge_page`.
4. `ChallengeResolver` resolve `MERCADOLIVRE_SNOOPY` (espera PoW, clica
   Continuar se preciso, espera JSON-LD / `.ui-pdp-price`).
5. Spider `MercadoLivreSpider` é **parse-only**: JSON-LD primeiro, fallback
   `itemprop=price` / widgets `ui-pdp-*`. Nunca inventa preço a partir do HTML
   de challenge.
6. Playwright **não** é adicionado; Camoufox permanece o fallback stealth.

## Justificativa

- Mitiga fingerprint TLS sem proxy pago no caminho feliz.
- Preserva Proxy Cost Mode e ADRs 0017/0018.
- Reutiliza Camoufox em vez de um segundo browser stack.
- Extração estruturada (JSON-LD) reduz dependência de seletores frágeis.

## Consequências positivas

- Loja `mercadolivre` no catálogo com playbook e testes de fixture.
- Métrica `fetch_strategy=curl-cffi-direct` quando HTTP basta.
- Challenge Snoopy deixa de ser “HTML de produto fantasma”.

## Trade-offs / consequências negativas

- Nova dependência `curl_cffi` (rebuild Docker necessário).
- IPs frios quase sempre caem no browser na primeira visita.
- Seller/GTIN podem faltar no JSON-LD; search/match ainda não habilitado.
