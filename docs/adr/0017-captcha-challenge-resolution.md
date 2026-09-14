# ADR 0017: Resolução obrigatória de challenge/CAPTCHA

- Status: Accepted
- Data: 2026-09-12

## Contexto

Versões anteriores da política do agente (ex.: trechos de `AGENTS.md` e notas
em ADR 0015/0016) orientavam a **detectar** challenge/CAPTCHA e falhar com
`UPSTREAM_BLOCKED` **sem** automatizar a resolução. Na operação real (Amazon e
outras lojas com WAF), isso deixa o fallback browser/proxy inutilizável quando
o challenge aparece, mesmo com HTTP-first cobrindo o caminho feliz.

O objetivo do ScoutApiV2 é coletar preços públicos apesar de WAF/anti-bot. O
README já afirma que o crawler visa contornar CAPTCHA/bloqueios para assegurar
a coleta.

## Problema / decisão necessária

Diante de challenge/CAPTCHA, o crawler deve falhar imediatamente ou **resolver**
o challenge e continuar a coleta?

## Alternativas consideradas

- **A — Fail-fast permanente:** detectar → `UPSTREAM_BLOCKED`; sem solver.
  Simples; abandona coleta no fallback.
- **B — Resolução obrigatória:** detectar → tentar resolver → só então
  `UPSTREAM_BLOCKED` se esgotar tentativas; nunca parsear HTML de bloqueio como
  produto.
- **C — Resolver só em lojas selecionadas:** inconsistente com o invariante
  global do crawler.

## Decisão

Adotar **B** como **regra crítica e inalterável**:

1. Challenge/CAPTCHA/robot-check **deve ser resolvido** quando encontrado.
2. Automação de resolução é permitida e esperada.
3. Página de challenge **nunca** vira `ProductOffer` / `available=false` /
   preço fabricado.
4. `UPSTREAM_BLOCKED` só após falha das tentativas de resolução (respeitando
   Proxy Cost Mode e a ordem HTTP → browser → proxy quando aplicável).
5. Mudanças de fetch/Camoufox necessárias para cumprir esta regra são
   autorizadas (exceção à imutabilidade padrão do scraper).

Esta ADR **supersede** a orientação anterior de “não automatizar CAPTCHA”
em `AGENTS.md` e trechos correlatos de ADR 0015 (§ bloqueio) e ADR 0016
(notas “sem CAPTCHA bypass”). HTTP-first (ADR 0016) permanece válido como
estratégia para **evitar** challenge; não substitui a obrigação de **resolver**
quando o challenge ocorrer.

## Justificativa

- Alinha política do agente ao objetivo declarado do crawler.
- Evita tratar anti-bot transitório como limitação de produto.
- Mantém fail-closed semântico: bloqueio ≠ OOS.

## Consequências positivas

- Fallback browser/proxy deixa de ser beco sem saída por política.
- Contrato claro: `ChallengeResolver` no `CamoufoxHtmlFetcher` + solver de
  imagem Amazon offline (`amazoncaptcha`, sem API key) controlado por
  `CAPTCHA_SOLVER_ENABLED` / `CAPTCHA_SOLVER_PROVIDER` /
  `CAPTCHA_SOLVER_MAX_ATTEMPTS`.

## Trade-offs / consequências negativas

- Manutenção quando o provedor de challenge mudar (ex.: novo tipo de CAPTCHA).
- `amazoncaptcha` resolve o captcha de texto clássico da Amazon; outros tipos
  (CF hard-block, Turnstile sem soft-resolve) ainda podem esgotar tentativas →
  `UPSTREAM_BLOCKED`.
- Pacote `amazoncaptcha` pinna Pillow antigo; o Docker/instalação usa
  `--no-deps` + Pillow moderno do `pyproject.toml` (ver
  `requirements-captcha.txt`).
