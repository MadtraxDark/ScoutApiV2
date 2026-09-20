.DEFAULT_GOAL := help

SHOPEE_SEED_URL ?= https://shopee.com.br/Kingston-HyperX-Fury-DDR4-PC-RAM-4-Gb-8-16-DDR4-2133-2400-2666-3200-Mhz-Mem%C3%B3ria-De-Mesa-i.341936748.29277977480

.PHONY: help spiders spiders-logs spiders-down seed-shopee seed-shopee-login up test test-unit test-integration test-live test-full lint format typecheck migrate

help:
	@echo "Comandos disponíveis:"
	@echo "  make spiders            Inicia a API com reload de spiders/services do crawler"
	@echo "  make spiders-logs       Mostra os logs da API em modo spiders"
	@echo "  make spiders-down       Para o ambiente em modo spiders"
	@echo "  make seed-shopee        Abre Camoufox headed para aquecer o profile (PDP Shopee)"
	@echo "  make seed-shopee-login  Abre a página de login da Shopee no Camoufox headed"
	@echo "  make up                 Inicia a API reconstruindo a imagem"
	@echo "  make migrate            Aplica migrations Alembic (DATABASE_URL)"
	@echo "  make test               Suite rápida (unit + integration determinística; exclui live/slow)"
	@echo "  make test-unit          Apenas tests/unit"
	@echo "  make test-integration   Apenas -m integration"
	@echo "  make test-live          Apenas -m live (rede real / lojas)"
	@echo "  make test-full          Suite completa (unit + integration + live + slow)"
	@echo "  make lint               Executa o Ruff"
	@echo "  make format             Valida a formatação"
	@echo "  make typecheck          Executa o mypy"

spiders:
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/update-spiders.ps1

spiders-logs:
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/update-spiders.ps1 logs

spiders-down:
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/update-spiders.ps1 down

seed-shopee:
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/seed-camoufox-profile.ps1 -Url "$(SHOPEE_SEED_URL)"

seed-shopee-login:
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/seed-camoufox-profile.ps1 -Login

up:
	docker compose up --build

migrate:
	alembic upgrade head

test:
	python -m pytest -m "not live and not slow"

test-unit:
	python -m pytest tests/unit -m "not live and not slow"

test-integration:
	python -m pytest -m "integration and not live and not slow"

test-live:
	python -m pytest -m live

test-full:
	python -m pytest

lint:
	ruff check .

format:
	ruff format --check .

typecheck:
	mypy src
