# ScoutApiV2

Base arquitetural de uma API FastAPI organizada como modular monolith e preparada para testes, CI/CD e execução via Docker.

## Requisitos

Python 3.12+; Docker e Docker Compose.

## Estrutura

`src/scout_api/api` contém a composição HTTP; `core` contém configuração e infraestrutura transversal; `modules` contém features; `tests` contém testes separados do código; `docs/adr` contém decisões arquiteturais.

## Configuração

Copie `.env.example` para `.env` e ajuste os valores conforme o ambiente. O `.env` é ignorado pelo Git e não deve conter valores versionados.

## Docker

Execute `docker compose up --build`. A API ficará disponível em `http://localhost:8000`; `GET /health` verifica a disponibilidade.

## Execução local

Execute `python -m venv .venv`, `python -m pip install -e ".[dev]"` e `uvicorn scout_api.main:app --reload --app-dir src`.

## Validação

Execute `python -m pytest`, `ruff check .`, `ruff format --check .` e `mypy src`.

## ADRs

As decisões ficam em [`docs/adr`](docs/adr/). Para uma nova decisão, copie [`docs/adr/template.md`](docs/adr/template.md), use o próximo número e registre contexto, alternativas, decisão, justificativa e consequências.
