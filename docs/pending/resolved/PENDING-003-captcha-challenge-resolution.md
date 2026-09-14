# PENDING-003 — Implementar resolução de challenge/CAPTCHA no fetch

- Status: RESOLVED
- Tipo: INCOMPLETE
- Prioridade: P0
- Área: crawler/fetch
- Resolvido: 2026-09-12

## Resolução

- `ChallengeResolver` + classificação (`challenge_resolution.py`)
- Wiring no `CamoufoxHtmlFetcher` (settle + pós-settle) antes de
  `UPSTREAM_BLOCKED`
- Solver de imagem offline `amazoncaptcha` (sem API key) via
  `CAPTCHA_SOLVER_*` em env / Compose / `.env.example`
- Soft-resolve Cloudflare JS (wait + Turnstile click)
- Testes: `tests/unit/test_challenge_resolution.py` (resolve ok / falha →
  blocked)
- Docs: ADR 0017, playbook Amazon, contracts
