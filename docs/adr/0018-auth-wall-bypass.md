# ADR 0018: Auth bypass obrigatório para paredes de login no crawler

- Status: Accepted
- Data: 2026-09-12

## Contexto

Lojas-alvo frequentemente intercalam **login wall**, soft-auth ou session-gate
antes da PDP/oferta pública. A política de pesquisa
(`research-and-problem-solving.mdc`) e restrições genéricas de “não quebrar
autenticação” poderiam ser lidas como proibição de contornar essas paredes —
o que tornaria a coleta inviável, na prática, em várias lojas.

O ScoutApiV2 já exige resolução de challenge/CAPTCHA (ADR 0017) e Proxy Cost
Mode (ADR 0014). Auth walls são a mesma classe de bloqueio operacional: não
são OOS e não são produto.

## Problema / decisão necessária

O crawler deve falhar ao encontrar login/auth wall, ou **deve obrigatoriamente
tentar auth bypass** (resolução/contorno de parede de login/sessão) para
continuar a coleta de preço público?

## Alternativas consideradas

- **A — Fail-fast em login wall:** detectar → `UPSTREAM_BLOCKED` sem tentativa.
  Simples; abandona coleta.
- **B — Auth bypass obrigatório no escopo do crawler:** resolver/contornar
  login/session gate com sessão própria / credenciais do operador / warmup;
  só então `UPSTREAM_BLOCKED`; nunca parsear login como produto.
- **C — Só lojas selecionadas:** inconsistente com o invariante global.

## Decisão

Adotar **B** como **regra crítica e inalterável**:

1. Auth wall / login gate / soft-auth que bloqueia oferta pública **deve ser
   resolvido ou contornado** (auth bypass de crawler).
2. Automação de sessão e login com secrets **locais do operador** é esperada.
3. Página de login/auth **nunca** vira `ProductOffer` / `available=false` /
   preço fabricado.
4. `UPSTREAM_BLOCKED` só após esgotar tentativas (respeitando Proxy Cost Mode).
5. Mudanças de fetch/Camoufox necessárias para cumprir esta regra são
   autorizadas.
6. **Não** autoriza roubo de credenciais de terceiros, ataque à API ScoutApiV2,
   nem versionar secrets no Git.

Complementa ADR 0017 (CAPTCHA); não a substitui.

## Justificativa

- Alinha política do agente ao objetivo de coleta apesar de WAF/anti-bot/auth
  soft.
- Evita misturar “não atacar sistemas alheios” com “não coletar preço público
  atrás de login wall da loja-alvo”.
- Mantém fail-closed semântico: auth wall ≠ OOS.

## Consequências positivas

- Agente não declara bloqueio prematuro por “auth é proibido”.
- Pesquisa externa (ADR/regra de research) pode incluir abordagens de sessão /
  login usadas por scrapers maduros, validadas e adaptadas.
- Fetch (`ChallengeResolver` + `is_auth_wall_page`) tenta soft-wait, login com
  credenciais de env e reabertura da PDP antes de `UPSTREAM_BLOCKED`.

## Trade-offs / consequências negativas

- Complexidade operacional (profiles, secrets locais, seed headed).
- Risco de manutenção quando a loja mudar o fluxo de login.
- Exige disciplina rigorosa: secrets fora do Git; escopo só lojas-alvo.
- Sem credenciais e sem sessão seeded, a tentativa ainda ocorre (re-nav /
  wait) mas pode esgotar → `UPSTREAM_BLOCKED` (esperado).
