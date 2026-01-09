#!/bin/bash
# LectulandiaExtractor - Script de ejecución simplificado

# Colores para output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔═══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   LectulandiaExtractor v0.2.0         ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════╝${NC}"
echo ""

# Verificar que estamos en el directorio correcto
if [ ! -f "scripts/CLI.py" ]; then
    echo -e "${YELLOW}⚠️  Error: Debes ejecutar este script desde el directorio raíz del proyecto${NC}"
    exit 1
fi

# Verificar que el entorno virtual existe
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}⚠️  Entorno virtual no encontrado. Ejecutando: uv sync${NC}"
    uv sync
fi

# Ejecutar el CLI con PYTHONPATH configurado
echo -e "${GREEN}✓ Iniciando CLI...${NC}"
echo ""

PYTHONPATH=. .venv/bin/python scripts/CLI.py "$@"
