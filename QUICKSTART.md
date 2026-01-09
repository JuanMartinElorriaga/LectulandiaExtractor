# 🚀 Quick Start - LectulandiaExtractor

## Instalación en 2 pasos

### 1. Instalar dependencias

```bash
uv sync
```

### 2. ¡Descargar libros!

```bash
sh run.sh --author "gabriel garcia marquez"
```

---

## ¿Qué pasa cuando ejecutas el comando?

1. Te muestra una lista de todos los libros del autor
2. Seleccionas cuáles quieres (escribe números separados por coma, o "ALL")
3. Descarga con progress bar visual
4. Al final te muestra un resumen

---

## Comandos más útiles

### Modo interactivo (más fácil)
```bash
./run.sh
```
Te pregunta todo paso a paso.

### Vista previa (ver qué hay sin descargar)
```bash
./run.sh --author "julio cortazar" --dry-run
```

### Con Makefile (más corto)
```bash
make download AUTHOR="borges"
```

---

## Configurar tus carpetas

Edita el archivo `.env`:

```bash
nano .env
```

Cambia esta línea:
```
DEFAULT_DOWNLOAD_FOLDER=/Users/jelorriaga/Downloads/Libros
```

Por tu carpeta preferida:
```
DEFAULT_DOWNLOAD_FOLDER=/Users/TU_USUARIO/MisCarpeta/Libros
```

---

## ¿Problemas?

### "No module named 'src'"
```bash
# Usa siempre ./run.sh en lugar de python directo
./run.sh --author "garcia marquez"
```

### Descargas muy lentas
```bash
# Edita .env y cambia:
REQUEST_DELAY_MIN=1.0
REQUEST_DELAY_MAX=2.0
```

---

## Ejemplos reales

### Descargar 3 libros específicos
```bash
./run.sh --author "isabel allende"
# Cuando te pregunte, escribe: 1,3,7
```

### Descargar todos los libros de un autor
```bash
./run.sh --author "mario vargas llosa"
# Cuando te pregunte, presiona Enter (default es ALL)
```

### Solo ver qué libros hay disponibles
```bash
./run.sh --author "octavio paz" --dry-run
```

---

## Ver logs

```bash
make logs
```

O manualmente:
```bash
tail -f logs/downloader_$(date +%Y-%m-%d).log
```

---

## Ayuda

```bash
./run.sh --help
make help
```

O lee el [README completo](README.md) para más detalles.

---

**¡Eso es todo! Ahora a disfrutar de la lectura 📚**
