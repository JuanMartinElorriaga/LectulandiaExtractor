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
- **Selección interactiva** - Checkboxes con Ctrl+A para seleccionar todos

### 🔧 Robustez
- **Retry automático** - Reintentos con backoff exponencial (502, 503, 504, 429)
- **Validación de EPUB** - Verifica integridad de archivos descargados
- **Anti-duplicados** - Fuzzy matching para evitar descargas repetidas
- **Rate limiting** - Delays aleatorios para evitar bloqueos

### 🎨 Interfaz
- **CLI interactiva** - Menús con InquirerPy
- **Progress bars** - Visualización con Rich
- **Modo dry-run** - Vista previa sin descargar

### 🔗 Integración
- **Calibre** - Sincronización automática con tu biblioteca
- **Configuración .env** - Personalizable

---

## 🛠️ Tecnologías

- **httpx** - Cliente HTTP moderno
- **BeautifulSoup4** - Parsing HTML
- **Rich** - Interfaz de terminal moderna
- **InquirerPy** - Menús interactivos
- **rapidfuzz** - Búsqueda fuzzy rápida
- **Tenacity** - Retry automático
- **Pydantic** - Configuración validada

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

### 4. ¡Ejecutar!

```bash
cd scripts && python CLI.py
```

---

## 📖 Uso

### Menú Principal

```
? ¿Qué deseas hacer?
  📝 Buscar por Autor
  📚 Buscar por Género
  ──────────────────────
  🔍 Buscar en Catálogo (2,500 libros)
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
├── config/
│   └── settings.py          # Configuración con pydantic
├── scripts/
│   ├── CLI.py               # Interfaz de línea de comandos
│   ├── extractor.py         # Lógica de descarga
│   ├── indexer.py           # Indexación del catálogo
│   ├── searcher.py          # Búsqueda fuzzy
│   └── calibre_utils.py     # Integración Calibre
├── src/
│   ├── infrastructure/
│   │   └── http/
│   │       └── http_client.py  # Cliente HTTP con retry
│   └── utils/
│       ├── validators.py       # Validación EPUB
│       └── delays.py           # Rate limiting
├── data/
│   └── catalog_index.json   # Índice local (gitignored)
├── logs/                    # Logs rotativos
├── .env                     # Tu configuración
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
# Ejecuta desde la carpeta scripts/
cd scripts && python CLI.py
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

## 🚧 Limitaciones

- Solo formato EPUB
- Requiere Calibre Desktop cerrado para sincronizar
- Dependiente de la estructura HTML de Lectulandia

---

## 🗺️ Roadmap

- [ ] Tests unitarios con pytest
- [ ] Exportación a CSV/JSON
- [ ] Soporte múltiples formatos (MOBI, PDF)
- [ ] GUI web con FastAPI
- [ ] Descargas concurrentes

---

## 🤝 Contribuir

1. Fork el proyecto
2. Crea una rama (`git checkout -b feature/AmazingFeature`)
3. Commit cambios (`git commit -m 'Add: AmazingFeature'`)
4. Push (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

---

## 📄 Licencia

Software libre. _Forked_ desde [LectulandiaExtractor](https://github.com/Sarrablo/LectulandiaExtractor).

---

## 🙏 Agradecimientos

- [Lectulandia](https://ww3.lectulandia.com/) - Literatura en español
- [Calibre](https://calibre-ebook.com/) - Gestor de ebooks

---

**Hecho con ❤️ para los amantes de la literatura en español**
