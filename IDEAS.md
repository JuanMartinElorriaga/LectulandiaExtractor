## Uso de agentes
- 1. Recomendador de Libros (RAG)
- 2. Búsqueda Conversacional
- 3. Curador de Biblioteca Personal, integrado con Calibre para armar colecciones reales
- 4. Agente de Descarga Autónomo
- 5. Generador de Metadata
- 6. Bibliotecario Personal

## Arquitectura draft
┌─────────────────────────────────────────┐
│              CLI / Chat UI              │
└────────────────────┬────────────────────┘
                     │
┌────────────────────▼────────────────────┐
│           LLM Agent (Claude)            │
│  ┌─────────────────────────────────┐    │
│  │  System Prompt:                 │    │
│  │  - Eres un bibliotecario       │    │
│  │  - Tienes acceso a tools       │    │
│  │  - Catálogo de 50k libros      │    │
│  └─────────────────────────────────┘    │
└────────────────────┬────────────────────┘
                     │ Tool Calls
    ┌────────────────┼────────────────┐
    ▼                ▼                ▼
┌───────┐      ┌──────────┐    ┌──────────┐
│Search │      │ Download │    │ Tracker  │
│Catalog│      │  Books   │    │  Stats   │
└───────┘      └──────────┘    └──────────┘
    │                │                │
    └────────────────┴────────────────┘
                     │
              ┌──────▼──────┐
              │   SQLite    │
              │  catalog.db │



## Libgen
- Libreria: grab-convert-from-libgen
- Aplicar lista de mirrors activos para rotar en caso de caida

## Open Library
- En caso de necesitar sinopsis de libros