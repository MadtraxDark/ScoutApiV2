.DEFAULT_GOAL := help

.PHONY: help spiders spiders-logs spiders-down up test lint format typecheck

help:
	@echo "Comandos disponíveis:"
	@echo "  make spiders       Inicia a API com reload de spiders/services do crawler"
	@echo "  make spiders-logs  Mostra os logs da API em modo spiders"
	@echo "  make spiders-down  Para o ambiente em modo spiders"
	@echo "  make up            Inicia a API reconstruindo a imagem"
	@echo "  make test          Executa os testes"
	@echo "  make lint          Executa o Ruff"
	@echo "  make format        Valida a formatação"
	@echo "  make typecheck     Executa o mypy"

spiders:
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/update-spiders.ps1

spiders-logs:
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/update-spiders.ps1 logs

spiders-down:
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/update-spiders.ps1 down

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
