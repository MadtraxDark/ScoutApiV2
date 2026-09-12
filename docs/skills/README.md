# Skills aprovadas

Skills são orientação versionada externamente, não dependências Python do projeto. A instalação ocorre no ambiente do Codex; os commits abaixo registram a revisão auditada em 12/09/2026.

| Skill | Origem | Revisão | Escopo aprovado |
|---|---|---|---|
| `fastapi` | `fastapi/fastapi`, `fastapi/.agents/skills/fastapi` | `50113da16fec53b66b80d75e80a89296de4fa5a5` | FastAPI, routers, DI, schemas e OpenAPI |
| `python-testing-patterns` | `wshobson/agents`, `plugins/python-development/skills/python-testing-patterns` | `a30778f8c4e6b0a87567941b7cca4f534bf642b6` | pytest, fixtures, mocks/fakes e testes de comportamento |
| `github-actions-templates` | `wshobson/agents`, `plugins/cicd-automation/skills/github-actions-templates` | `a30778f8c4e6b0a87567941b7cca4f534bf642b6` | `.github/workflows/` e somente CI/CD solicitado |
| `code-review-excellence` | `wshobson/agents`, `plugins/developer-essentials/skills/code-review-excellence` | `a30778f8c4e6b0a87567941b7cca4f534bf642b6` | revisão de mudanças, regressões, segurança e arquitetura |
| `skill-scanner` | `getsentry/skills`, `skills/skill-scanner` | `c2f99a5b04b4cd992ec3022d7c2c3e23e938d241` | auditoria prévia de skills de terceiros |
| `api-security-review` | `OWASP/secure-agent-playbook`, `plugins/code-security-skills/skills/api-security-review` | `79fea6b9115b55687818f8c4073844ee9ba907a6` | revisão autorizada de API, validação, SSRF e contratos |
| `scrapy-web-scraping` | `mindrally/skills`, `scrapy-web-scraping` | `97184105b5daa3a6860a2aeb8e7e7fd1c42da40a6` | parsing, selectors e robustez conceitual do crawler |
| `find-skills` | `rohitg00/skillkit`, `skills/find-skills` | `d2e5c346f73325c326820efd3188dcf2b6eb704f` | descoberta e triagem de skills; não instala nada sem auditoria |

Auditoria: o scan estático de `find-skills` não encontrou findings; há um URL externo (`agentskills.com`) e comandos `npx skillkit@latest` documentais. Eles não foram executados. A regra local exige revisão/pinning antes de qualquer instalação. O repositório SkillKit é um monorepo/CLI, não uma skill única; suas 15 metodologias internas não foram instaladas. Dois módulos internos apresentaram somente warning de consistência entre nome do diretório e frontmatter (`structured-review` e `anti-patterns`). A skill do Scrapy não autoriza migração para Scrapy, e a skill de segurança não autoriza testes ativos contra terceiros.
