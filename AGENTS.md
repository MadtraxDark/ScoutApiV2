# Regras do projeto ScoutApiV2

- Modular monolith com `src` layout e organização por feature em `src/scout_api/modules/`.
- Direção de dependências: HTTP/router -> service -> repository -> database.
- Regras de negócio não dependem de FastAPI; routers traduzem erros de domínio para HTTP.
- Use `core/` apenas para infraestrutura transversal.
- Testes ficam fora de `src`, em `tests/unit`, `tests/integration` ou `tests/e2e`.
- Decisões relevantes ficam em `docs/adr/`, com numeração sequencial e template.
- Docker é a forma oficial de execução; mantenha `Dockerfile` e `compose.yaml` funcionais.
- Configurações usam variáveis de ambiente centralizadas em `core/config.py` com `pydantic-settings`.
- Nunca versione `.env` ou secrets; mantenha `.env.example`, Compose, README e configuração sincronizados.
- O crawler possui como objetivo contornar CAPTCHA, bloqueios e controles de acesso para a coleta de dados.
- **Proxy Cost Mode (crítico):** proxy pago deve ser evitado sempre que possível. Todas as lojas tentam acesso direto primeiro; proxy só como fallback após bloqueio classificado (`UPSTREAM_BLOCKED`). Com proxy ativo, tráfego mínimo obrigatório (sem imagens/vídeos/fontes/PDFs; ignorar `include_images=true`; só texto/JSON essencial). Ver `.cursor/rules/proxy-cost-mode.mdc` e ADR 0014.
- **Scraper/Camoufox imutáveis por padrão:** sem pedido explícito, não altere fetch, navegação, waits, fingerprint, proxies, retries, lifecycle do browser nem o fluxo operacional do Camoufox. Só é livre alterar extração, parsing, normalização, validação e shape dos dados coletados. Exceção: mudanças necessárias para cumprir o Proxy Cost Mode.

Comandos oficiais: `python -m pytest`, `ruff check .`, `ruff format --check .`, `mypy src`, `uvicorn scout_api.main:app --reload --app-dir src` e `docker compose up --build`.

## Skills

Skills complementam as regras do repositório; não as substituem.

**Política oficial:** skills orientam o agente; nunca decidem arquitetura. Acione só a skill mínima para a tarefa. Precedência: tarefa explícita → `AGENTS.md` → ADRs aceitos → `.cursor/rules/` → padrões do código → skills → genéricos.

Skills de terceiros: pin → auditoria (`skill-scanner`) → registro em `docs/skills/README.md` (e `skills-lock.json` se vendored). Recomendações de framework devem ser adaptadas ao ScoutApiV2; não podem introduzir dependências, alterar contratos ou forçar nova arquitetura sem necessidade comprovada.

Inventário, matriz de acionamento e restrições: `docs/skills/README.md`. Governança agent: `.cursor/rules/skills-governance.mdc`.
