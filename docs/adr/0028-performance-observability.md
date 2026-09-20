# ADR-0028: Observabilidade de tempo e budgets de performance

- Status: Accepted
- Data: 2026-09-20

## Contexto

Processos longos (runtime, testes, crawler, Product Match, browser, DB, CI e
comandos executados por agentes) frequentemente ficavam invisíveis até o fim da
tarefa. Isso impedia localizar gargalos, retries e trabalho duplicado.

## Problema / decisão necessária

Como tornar operações anormalmente longas visíveis e investigáveis sem poluir
logs, sem magic numbers espalhados e sem mudar o comportamento operacional do
Camoufox/scraper?

## Alternativas consideradas

- APM/vendor pago completo — rejeitado como default (custo; preferir nativo/OSS
  primeiro; alinhar a research-and-problem-solving).
- Um único threshold global — rejeitado (unit ≠ live scrape).
- Só `--durations` no pytest — insuficiente para runtime/retries/browser.
- Instrumentar cada seletor/wait interno do Camoufox — rejeitado (ruído +
  conflito com scraper-camoufox-immutable); medir nas fronteiras (launch/fetch).

## Decisão

1. Módulo central `scout_api.core.performance` com severidades
   `NORMAL|WARN|SLOW|CRITICAL`, budgets por `OperationCategory`, `observe` /
   `timed`, `RetryLedger` e `DuplicateWorkTracker`.
2. Instrumentar fronteiras já existentes (match timing, fetch metrics, retries,
   DB cursor execute, pytest hooks).
3. Documentar política canônica em `docs/performance.md` + regra always-on
   `.cursor/rules/performance.mdc` + invariante curto em `AGENTS.md`.
4. Tipo de pendência `PERFORMANCE` para regressões recorrentes não resolvidas.

## Justificativa

Medir nas fronteiras reutiliza telemetria existente (`match_*_timing`,
`fetch_cost_metrics`), evita alterar navegação Camoufox e atende o invariante
“processo longo não pode ser invisível” também para agentes.

## Consequências positivas

- Slow paths e retries ficam explícitos nos logs.
- Budgets únicos e revisáveis.
- Agentes têm regra operacional clara (não esperar silenciosamente; feedback
  rápido; reportar regressão).

## Trade-offs / consequências negativas

- Mais linhas de log em WARN+ (mitigado: NORMAL é silencioso).
- Listener SQLAlchemy adiciona overhead mínimo por query (só emite ≥ WARN).
- Thresholds iniciais são heurísticos — calibrar com baselines em
  `docs/performance/baselines.md`.
