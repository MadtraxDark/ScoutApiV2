# Skills aprovadas

Skills são orientação versionada externamente, não dependências Python do projeto.
Não alteram a arquitetura do ScoutApiV2 só porque recomendam outro padrão.

## Política oficial

1. Skills orientam o agente; **nunca** decidem arquitetura.
2. Acione **somente** a skill mínima necessária para a tarefa.
3. Em conflito, prevalece esta ordem:
   1. requisito explícito da tarefa;
   2. `AGENTS.md`;
   3. ADRs aceitos em `docs/adr/`;
   4. `.cursor/rules/`;
   5. padrões reais do codebase;
   6. skills;
   7. recomendações genéricas.
4. **Scrapy skill** = parsing, selectors, normalização e testes. Não migrar fetch,
   middleware, scheduler, Splash/Playwright, Scrapy-Redis nem proxy rotation.
5. **Camoufox / proxy / navegação** = intocáveis sem pedido explícito
   (exceção: Proxy Cost Mode — ADR 0014).
6. **Nova skill de terceiro** (gate obrigatório):
   1. descoberta opcional (`find-skills`, sem auto-install);
   2. pin de origem/revisão;
   3. auditoria com `skill-scanner`;
   4. registro neste arquivo com escopo aprovado;
   5. atualizar `skills-lock.json` se a skill for vendored em `.agents/skills/`.
7. Não execute `npx skillkit@latest` automaticamente. Não rode scripts, hooks ou
   downloads de skill sem revisão explícita.
8. Não invente ferramentas de lint/type-check/CI, auth, gateway ou ORM só porque
   uma skill lista isso.

## Inventário e localização

Há duas camadas. Ambas só valem no escopo aprovado abaixo.

| Camada | Onde | O que registra |
|---|---|---|
| **Projeto (vendored)** | `.agents/skills/` + `skills-lock.json` | skills versionadas no repositório |
| **Codex (user)** | `~/.codex/skills/` | skills auditadas no ambiente do agente |

`skills-lock.json` cobre apenas skills vendored no projeto. Skills Codex aprovadas
ficam neste README com commit/revisão; não invente entradas de lock para elas.

## Skills aprovadas

Revisão registrada em 12/09/2026.

### Vendored no projeto (`.agents/skills/`)

| Skill | Origem | Lock | Escopo aprovado | Uso |
|---|---|---|---|---|
| `docker` | `mindrally/skills` | `skills-lock.json` | Dockerfile, Compose, runtime container | MUITO ÚTIL |
| `dockerfile-optimise` | `pproenca/dot-skills` | `skills-lock.json` | otimização explícita de Dockerfile | ÚTIL EM CASOS ESPECÍFICOS |
| `browser-use` | `browser-use/plugins` @ `4749bcb` (`cursor/skills/browser-use`) | `skills-lock.json` | validação UI / navegação **do agente** (Chrome CDP ou cloud sob pedido); **não** substitui Camoufox/fetch do crawler | ÚTIL EM CASOS ESPECÍFICOS |
| `supabase-postgres` | projeto (ScoutApiV2) | n/a (first-party) | `DATABASE_URL`, SQLAlchemy, Alembic, repositories, health/pool/SSL Supabase; **sem** Data API | MUITO ÚTIL |

### Codex (user), auditadas

| Skill | Origem | Revisão | Escopo aprovado | Uso |
|---|---|---|---|---|
| `fastapi` | `fastapi/fastapi`, `fastapi/.agents/skills/fastapi` | `50113da16fec53b66b80d75e80a89296de4fa5a5` | routers, DI, schemas, OpenAPI | MUITO ÚTIL |
| `python-testing-patterns` | `wshobson/agents`, `plugins/python-development/skills/python-testing-patterns` | `a30778f8c4e6b0a87567941b7cca4f534bf642b6` | pytest, fixtures, fakes, regressão | MUITO ÚTIL |
| `github-actions-templates` | `wshobson/agents`, `plugins/cicd-automation/skills/github-actions-templates` | `a30778f8c4e6b0a87567941b7cca4f534bf642b6` | `.github/workflows/` sob pedido | ÚTIL EM CASOS ESPECÍFICOS |
| `code-review-excellence` | `wshobson/agents`, `plugins/developer-essentials/skills/code-review-excellence` | `a30778f8c4e6b0a87567941b7cca4f534bf642b6` | review por risco (ver critérios) | MUITO ÚTIL* |
| `skill-scanner` | `getsentry/skills`, `skills/skill-scanner` | `c2f99a5b04b4cd992ec3022d7c2c3e23e938d241` | auditoria de skills de terceiros | ESSENCIAL |
| `api-security-review` | `OWASP/secure-agent-playbook`, `plugins/code-security-skills/skills/api-security-review` | `79fea6b9115b55687818f8c4073844ee9ba907a6` | URL/SSRF, validação, limites, OpenAPI | MUITO ÚTIL |
| `scrapy-web-scraping` | `mindrally/skills`, `scrapy-web-scraping` | `97184105b5daa3a6860a2aeb8e7e7fd1c42da40a6` | parsing/selectors **conceitual** | ÚTIL EM CASOS ESPECÍFICOS |
| `find-skills` | `rohitg00/skillkit`, `skills/find-skills` | `d2e5c346f73325c326820efd3188dcf2b6eb704f` | descoberta; sem install automático | BAIXA PRIORIDADE |

\*Acionar só com critério de risco (ver matriz e `.cursor/rules/code-review.mdc`).

### Notas de auditoria

- Scan estático de `find-skills`: sem findings críticos; URL externo (`agentskills.com`)
  e `npx skillkit@latest` são documentais — **não executados** na adoção.
- SkillKit é monorepo/CLI; metodologias internas não foram instaladas.
- `scrapy-web-scraping` **não** autoriza migração operacional para Scrapy.
- `api-security-review` **não** autoriza testes ativos contra terceiros.
- `browser-use` (2026-09-14): origem `browser-use/plugins` commit
  `4749bcbfe456e5384b98281a8a66119352197f59`; `skill-scanner` = 0 findings.
  Plugin Cursor em `~/.cursor/plugins/local/browser-use` + skill vendored em
  `.agents/skills/browser-use/`. MCP upstream usa `uvx browser-use@latest`
  (não pinado pelo vendor). **Não** substitui Camoufox/fetch; Browser Use Cloud
  / API key só com autorização explícita. Chrome local exige remote debugging.

## Matriz de acionamento

| Tipo de tarefa | Skills recomendadas | Não acionar |
|---|---|---|
| Endpoint FastAPI | `fastapi` | scrapy, GHA, dockerfile-optimise |
| Bug / regressão | `python-testing-patterns` | scrapy-full, GHA |
| Novo spider / adapter | scrapy (**só parsing/selectors**), testing; code-review se relevante | Splash/Playwright/Redis/proxy rotation |
| Parser / fixtures | testing (+ scrapy conceitual) | fastapi, GHA, OWASP full |
| Fetch / browser / proxy | nenhuma skill — ADRs/rules; code-review se pedido explícito | scrapy, fastapi |
| Validação visual de site (agente) | `browser-use` (Chrome CDP / plugin Cursor) | trocar Camoufox; cloud pago sem auth |
| Teste | `python-testing-patterns` | api-security (salvo validação SSRF) |
| Security (URL, secrets, limites) | `api-security-review` | scrapy, find-skills |
| CI | `github-actions-templates` | fastapi, scrapy |
| Docker / Compose | `docker`; `dockerfile-optimise` só se otimizar imagem | scrapy |
| Persistência / Supabase / migrations | `supabase-postgres` | Data API, supabase-py, SQL em services |
| Refactor arquitetural | code-review + skill da área | find-skills |
| Code review | `code-review-excellence` se risco | empilhar várias skills sem benefício |
| Nova skill de terceiro | `skill-scanner` → registro; `find-skills` só para busca | install sem scan |

## Critérios para `code-review-excellence`

Acionar quando **qualquer** item for verdadeiro:

- novo spider/store adapter;
- mudança em fetch, Camoufox, proxy, concorrência, retry ou cache;
- mudança de contrato Offer / Details / Images;
- refactor arquitetural ou ADR;
- surface de segurança (URL, secrets, Docker, erros/logs);
- PR/diff grande (~200+ linhas) ou cross-cutting.

**Não** acionar para typo, rename, docs, ajuste cosmético ou teste trivial.

## CI recomendado (quando solicitado)

Ordem sugerida; comandos oficiais do projeto; **sem deploy** sem pedido explícito:

1. `ruff check .`
2. `ruff format --check .`
3. `mypy src`
4. `python -m pytest`
5. opcional: build da imagem / `docker compose build`

Python **3.12**; actions pinadas; sem matrix Node/K8s/Slack por template.

## O que skills NÃO devem introduzir

- Scrapy Splash / Playwright / Scrapy-Redis / fake-UA / proxy rotation
- Migração do fetch Camoufox (incl. trocar por Browser Use Cloud/CLI no crawler)
- SQLModel / ORM / repository “preventivo”
- Supabase Data API / PostgREST / acesso frontend ao Postgres
- Frontend embutido no FastAPI / SSE
- Alpine ou distroless sem prova de que Camoufox continua funcional
- API Gateway, JWT/OAuth ou WAF só por checklist
- Ferramentas fora de `pyproject.toml` / `AGENTS.md` (`ty`, `fastapi CLI` como padrão, etc.)
- freezegun / Hypothesis / pytest-asyncio sem problema real comprovado

## Recomendações de manutenção

### Alta prioridade

- Manter este README, `AGENTS.md` e `.cursor/rules/skills-governance.mdc` alinhados.
- Manter `skills-lock.json` sincronizado com `.agents/skills/` (camada vendored).
- Gate `skill-scanner` antes de qualquer skill nova.
- Quando houver pedido de CI: workflow mínimo com os comandos oficiais acima.

### Média prioridade

- Preferir `docker` no dia a dia; `dockerfile-optimise` só em otimização explícita.
- Reavaliar escopo de `find-skills` (uso raro; risco de supply chain).
- Melhorar testes com parametrização/fixtures (sem refactor amplo só por skill).

### Baixa prioridade

- Consolidar narrativa Docker no README se o lock ganhar mais skills de imagem.
- E2e live contra marketplaces: não priorizar.

## Referências

- Governança agent: `.cursor/rules/skills-governance.mdc`
- FastAPI / testing / crawler / security / CI / code-review: `.cursor/rules/`
- Arquitetura: `AGENTS.md`, `docs/adr/`
