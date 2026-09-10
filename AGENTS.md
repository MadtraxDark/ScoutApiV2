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
- **Scraper/Camoufox imutáveis por padrão:** sem pedido explícito, não altere fetch, navegação, waits, fingerprint, proxies, retries, lifecycle do browser nem o fluxo operacional do Camoufox. Só é livre alterar extração, parsing, normalização, validação e shape dos dados coletados.

Comandos oficiais: `python -m pytest`, `ruff check .`, `ruff format --check .`, `mypy src`, `uvicorn scout_api.main:app --reload --app-dir src` e `docker compose up --build`.
