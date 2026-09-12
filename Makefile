.DEFAULT_GOAL := help

SHOPEE_SEED_URL ?= https://shopee.com.br/Kingston-HyperX-Fury-DDR4-PC-RAM-4-Gb-8-16-DDR4-2133-2400-2666-3200-Mhz-Mem%C3%B3ria-De-Mesa-i.341936748.29277977480

.PHONY: help spiders spiders-logs spiders-down seed-shopee seed-shopee-login up test lint format typecheck

help:
	@echo "Comandos disponíveis:"
	@echo "  make spiders            Inicia a API com reload de spiders/services do crawler"
	@echo "  make spiders-logs       Mostra os logs da API em modo spiders"
	@echo "  make spiders-down       Para o ambiente em modo spiders"
	@echo "  make seed-shopee        Abre Camoufox headed para aquecer o profile (PDP Shopee)"
	@echo "  make seed-shopee-login  Abre a página de login da Shopee no Camoufox headed"
	@echo "  make up                 Inicia a API reconstruindo a imagem"
	@echo "  make test               Executa os testes"
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

test:
	python -m pytest

lint:
	ruff check .

format:
	ruff format --check .

typecheck:
	mypy src
