# LectulandiaExtractor

> **_Las personas libres jamás podrán concebir lo que los libros significan para quienes vivimos encerrados_**

## Descripción

Herramienta para descargar libros en **español** en formato **EPUB** programáticamente desde [Lectulandia](https://ww3.lectulandia.com/).

El programa permite buscar por autor, género o en un catálogo local indexado, seleccionar libros interactivamente y descargarlos de forma organizada.

> El objetivo es facilitar y automatizar el proceso de armado de una biblioteca digital ordenada y rápida.

---

## ✨ Características

### 📚 Búsqueda y Descarga
- **Búsqueda por autor** - Encuentra todos los libros de un autor
- **Búsqueda por género** - Navega libros por categoría
- **Catálogo local indexado** - Búsqueda rápida offline por título o autor
- **Selección interactiva** - Checkboxes con accesos de teclado para interacción dinámica

### 🔧 Robustez
- **Retry automático** - Reintentos con backoff exponencial
- **Validación de EPUB** - Verifica integridad de archivos descargados
- **Anti-duplicados** - Detección vía base de datos + fuzzy matching
- **Rate limiting** - Delays aleatorios y header rotation para evitar bloqueos
- **Resume/Checkpoint** - Continúa descargas e indexaciones interrumpidas
- **Tracking de descargas** - Registro persistente en SQLite

### 🎨 Interfaz
- **CLI interactiva** - Menús con `InquirerPy`
- **Progress bars** - Visualización con `Rich`
- **Modo dry-run** - Vista previa sin descargar

### 🔗 Integración
- **Calibre** - Sincronización automática con tu biblioteca (opcional)
- **Configuración .env** - Parámetros personalizable

---

## 🛠️ Tecnologías

- **httpx** - Cliente HTTP moderno
- **BeautifulSoup4** - Parsing HTML
- **SQLite + FTS5** - Base de datos con búsqueda full-text
- **Rich** - Interfaz de terminal moderna
- **InquirerPy** - Menús interactivos
- **rapidfuzz** - Búsqueda fuzzy rápida
- **Tenacity** - Retry automático
- **Pydantic** - Configuración validada
- **pytest** - Testing

---

## 🚀 Inicio Rápido

### 1. Instalar UV (gestor de paquetes)

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# O con brew (macOS)
brew install uv
```

### 2. Clonar e Instalar

```bash
git clone https://github.com/JuanMartinElorriaga/LectulandiaExtractor.git
cd LectulandiaExtractor
uv sync
```

### 3. Configurar (Opcional)

```bash
cp .env.example .env
nano .env
```

```bash
DEFAULT_DOWNLOAD_FOLDER=/Users/tu_usuario/Downloads/Libros
DEFAULT_CALIBRE_LIBRARY=/Users/tu_usuario/CalibreLibrary
```

### 4. Ejecutar!

```bash
sh run.sh
```

---

## 📖 Uso

### Menú Principal

```
? ¿Qué deseas hacer?
  🔍 Buscar en Catálogo (50,000 libros)
  📚 Buscar por Género
  📝 Buscar por Autor
  ──────────────────────
  📊 Estado de descargas
  ⏯️  Reanudar operación (2 pendientes)
  📁 Sincronizar descargas
  ──────────────────────
  🔄 Actualizar Índice (solo nuevos)
  🔁 Reconstruir Índice (desde cero)
  ──────────────────────
  ❌ Salir
```

### 📝 Buscar por Autor

Ingresa el nombre de un autor y selecciona los libros a descargar:

```
? Nombre del autor: gabriel garcia marquez

📚 41 libros encontrados

? Seleccionar libros para descargar
  ○ Cien Años De Soledad
  ○ El Amor En Los Tiempos Del Cólera
  ● Crónica De Una Muerte Anunciada
  ...
```

### 📚 Buscar por Género

Selecciona un género con búsqueda fuzzy:

```
? Seleccionar género: fant

❯ Fantasía (1,234 libros)
  Fantasía Épica
  Fantasía Urbana
```

### 🔍 Buscar en Catálogo

Búsqueda rápida en el índice local:

```
? ¿Qué deseas buscar?
  📖 Buscar por título
  ✍️  Buscar por autor
  🔍 Buscar en todo
  ← Volver

? Buscar autor: Cortázar

╭─────────── Resultados para: 'Cortázar' ───────────╮
│  #  │ Título              │ Autor           │ Match │
├─────┼─────────────────────┼─────────────────┼───────┤
│  1  │ Rayuela             │ Julio Cortázar  │  95%  │
│  2  │ Bestiario           │ Julio Cortázar  │  92%  │
│  3  │ Final Del Juego     │ Julio Cortázar  │  88%  │
╰───────────────────────────────────────────────────╯
```

### 🔄 Gestión del Índice

- **Actualizar**: Revisa N páginas buscando libros nuevos
- **Reconstruir**: Elimina el índice y lo construye desde cero

```
? Páginas a indexar (0 = todas): 20

🔁 Reconstruyendo índice desde cero...

Página 15 ████████████████████ 360 libros   00:25

✅ Índice construido!
   📚 360 libros indexados
   📄 15 páginas procesadas
```

### 📊 Estado y Tracking

**Estado de descargas** - Ver estadísticas de tus descargas:

```
📊 Estado de Descargas

┌────────────────────────┬──────────┐
│ Estado                 │ Cantidad │
├────────────────────────┼──────────┤
│ ✅ Descargados          │      245 │
│ ⏭️  Omitidos (duplicados)│       38 │
│ ❌ Fallidos             │        5 │
└────────────────────────┴──────────┘

Tasa de éxito: 98.3% (283/288)
```

**Reanudar operación** - Continúa descargas o indexaciones interrumpidas:

```
? Seleccionar operación a reanudar
❯ Descarga por autor: García Márquez - 45/100 (45%)
  Reconstrucción de índice - 120/500 (24%)
  ← Cancelar
```

**Sincronizar descargas** - Registra EPUBs existentes en la base de datos:

```
📁 Sincronizar Descargas

┌─────────────────────┬──────────┐
│ Resultado           │ Cantidad │
├─────────────────────┼──────────┤
│ 📚 EPUBs encontrados │      156 │
│ ✅ Nuevos registrados │      142 │
│ ⏭️  Ya registrados    │       14 │
└─────────────────────┴──────────┘
```

---

## 📁 Estructura de Archivos

### Descargas por Autor

```
downloads/
└── Gabriel Garcia Marquez/
    ├── Cien años de soledad/
    │   └── Cien años de soledad.epub
    └── El amor en los tiempos del cólera/
        └── El amor en los tiempos del cólera.epub
```

### Descargas por Género

```
downloads/
└── Fantasía/
    └── Brandon Sanderson/
        └── El Imperio Final/
            └── El Imperio Final.epub
```

### Proyecto

```
LectulandiaExtractor/
├── .github/
│   └── workflows/
│       └── ci.yml              # CI con GitHub Actions
├── config/
│   └── settings.py             # Configuración con pydantic
├── scripts/
│   ├── CLI.py                  # Interfaz de línea de comandos
│   ├── extractor.py            # Lógica de descarga
│   ├── indexer.py              # Indexación del catálogo
│   ├── searcher.py             # Búsqueda fuzzy
│   ├── database.py             # SQLite + FTS5 para búsquedas
│   ├── download_tracker.py     # Tracking de descargas
│   ├── operations.py           # Checkpoint/Resume
│   └── calibre_utils.py        # Integración Calibre
├── src/
│   ├── infrastructure/
│   │   └── http/
│   │       └── http_client.py  # Cliente HTTP con retry
│   └── utils/
│       ├── validators.py       # Validación EPUB
│       └── delays.py           # Rate limiting
├── tests/                      # Tests con pytest
├── data/
│   └── catalog.db              # Base de datos SQLite (gitignored)
├── logs/                       # Logs rotativos
├── .env                        # Tu configuración
└── README.md
```

---

## 🔧 Configuración

### Archivo .env

```bash
# Carpetas
DEFAULT_DOWNLOAD_FOLDER=/Users/tu_usuario/Downloads/Libros
DEFAULT_CALIBRE_LIBRARY=/Users/tu_usuario/CalibreLibrary

# Rate Limiting
REQUEST_DELAY_MIN=2.0
REQUEST_DELAY_MAX=5.0
MAX_RETRIES=3

# Fuzzy Matching (0-100)
AUTHOR_MATCH_THRESHOLD=90
BOOK_MATCH_THRESHOLD=90

# Timeouts (segundos)
DOWNLOAD_TIMEOUT=180
REQUEST_TIMEOUT=30
```

---

## 🐛 Troubleshooting

### "No module named 'src'"

```bash
# Ejecuta desde el bash script la carpeta scripts, no desde python directamente
sh bash.sh
```

### "calibredb: command not found"

```bash
# macOS: Agregar Calibre al PATH
export PATH="/Applications/calibre.app/Contents/MacOS:$PATH"
```

### Descargas fallidas

```bash
# Aumenta delays en .env
REQUEST_DELAY_MIN=3.0
REQUEST_DELAY_MAX=7.0
```

---

## 🧪 Tests

```bash
# Ejecutar todos los tests
uv run pytest

# Tests con coverage
uv run pytest --cov=scripts --cov=src --cov-report=term-missing

# Solo tests específicos
uv run pytest tests/test_download_tracker.py -v
```

El proyecto incluye CI con GitHub Actions que ejecuta tests automáticamente en Python 3.12 y 3.13.

---

## 🤝 Contribuir

1. Fork el proyecto
2. Crea una rama (`git checkout -b feature/AmazingFeature`)
3. Ejecuta los tests (`uv run pytest`)
4. Commit cambios (`git commit -m 'Add: AmazingFeature'`)
5. Push (`git push origin feature/AmazingFeature`)
6. Abre un Pull Request

---

## 📄 Licencia

Software libre. _Forked_ desde [LectulandiaExtractor](https://github.com/Sarrablo/LectulandiaExtractor).


---

**Hecho con ❤️ para los amantes de la literatura en español**
