.PHONY: help install run test clean

help: ## Mostrar ayuda
	@echo "LectulandiaExtractor - Comandos disponibles:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Instalar dependencias
	@echo "📦 Instalando dependencias..."
	uv sync
	@echo "✅ Dependencias instaladas"

run: ## Ejecutar el CLI (interactivo)
	@./run.sh

download: ## Descargar libros de un autor (uso: make download AUTHOR="garcia marquez")
	@./run.sh --author "$(AUTHOR)"

dry-run: ## Vista previa sin descargar (uso: make dry-run AUTHOR="borges")
	@./run.sh --author "$(AUTHOR)" --dry-run

test: ## Ejecutar tests (cuando estén implementados)
	@echo "🧪 Ejecutando tests..."
	PYTHONPATH=. .venv/bin/pytest tests/ -v

clean: ## Limpiar archivos temporales y caché
	@echo "🧹 Limpiando archivos temporales..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@rm -rf .pytest_cache 2>/dev/null || true
	@echo "✅ Limpieza completada"

logs: ## Ver logs recientes
	@echo "📋 Logs recientes:"
	@tail -n 50 logs/downloader_*.log 2>/dev/null || echo "No hay logs disponibles"

.DEFAULT_GOAL := help
