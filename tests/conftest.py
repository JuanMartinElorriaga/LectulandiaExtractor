"""
Shared pytest fixtures for LectulandiaExtractor tests.
"""

import sys
import sqlite3
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """
    Create a temporary SQLite database for tests.
    
    Patches the DB_FILE path so all database operations use the temp DB.
    """
    db_path = tmp_path / "test_catalog.db"
    
    # Patch the database module's DB_FILE
    import database as db
    monkeypatch.setattr(db, "DB_FILE", db_path)
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    
    # Initialize the database
    db.init_db()
    
    yield db_path
    
    # Cleanup is automatic with tmp_path


@pytest.fixture
def sample_books():
    """
    Return a list of sample book dictionaries for testing.
    """
    return [
        {
            "title": "Cien Anos De Soledad",
            "author": "Gabriel García Márquez",
            "slug": "cien-anos-de-soledad",
            "url": "https://ww3.lectulandia.com/book/cien-anos-de-soledad/",
        },
        {
            "title": "El Amor En Los Tiempos Del Colera",
            "author": "Gabriel García Márquez",
            "slug": "el-amor-en-los-tiempos-del-colera",
            "url": "https://ww3.lectulandia.com/book/el-amor-en-los-tiempos-del-colera/",
        },
        {
            "title": "Rayuela",
            "author": "Julio Cortázar",
            "slug": "rayuela",
            "url": "https://ww3.lectulandia.com/book/rayuela/",
        },
        {
            "title": "La Casa De Los Espiritus",
            "author": "Isabel Allende",
            "slug": "la-casa-de-los-espiritus",
            "url": "https://ww3.lectulandia.com/book/la-casa-de-los-espiritus/",
        },
        {
            "title": "Pedro Paramo",
            "author": "Juan Rulfo",
            "slug": "pedro-paramo",
            "url": "https://ww3.lectulandia.com/book/pedro-paramo/",
        },
    ]


@pytest.fixture
def sample_books_no_author():
    """
    Return sample books without author information.
    """
    return [
        {
            "title": "Libro Sin Autor",
            "slug": "libro-sin-autor",
            "url": "https://ww3.lectulandia.com/book/libro-sin-autor/",
        },
    ]


@pytest.fixture
def sample_html():
    """
    Return sample Lectulandia HTML page for parsing tests.
    """
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Lectulandia - Books</title></head>
    <body>
        <main>
            <article class="book-card">
                <div class="card-content">
                    <a class="card-click-target" href="/book/cien-anos-de-soledad/"></a>
                    <a href="/autor/gabriel-garcia-marquez/" rel="tag">Gabriel García Márquez</a>
                </div>
            </article>
            <article class="book-card">
                <div class="card-content">
                    <a class="card-click-target" href="/book/rayuela/"></a>
                    <a href="/autor/julio-cortazar/" rel="tag">Julio Cortázar</a>
                </div>
            </article>
            <article class="book-card">
                <div class="card-content">
                    <a class="card-click-target" href="/book/libro-sin-autor/"></a>
                    <!-- No author link -->
                </div>
            </article>
            <a class="next page-numbers" href="/book/page/2/">Next</a>
        </main>
    </body>
    </html>
    """


@pytest.fixture
def sample_html_no_next_page():
    """
    Return sample HTML without next page link (last page).
    """
    return """
    <!DOCTYPE html>
    <html>
    <body>
        <main>
            <article class="book-card">
                <div class="card-content">
                    <a class="card-click-target" href="/book/ultimo-libro/"></a>
                    <a href="/autor/autor-final/" rel="tag">Autor Final</a>
                </div>
            </article>
            <!-- No next page link -->
        </main>
    </body>
    </html>
    """


@pytest.fixture
def valid_epub(tmp_path):
    """
    Create a valid EPUB file for testing.
    """
    epub_path = tmp_path / "valid_book.epub"
    
    with zipfile.ZipFile(epub_path, 'w') as zf:
        # EPUB must have mimetype as first file
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>""")
        zf.writestr("content.opf", """<?xml version="1.0"?>
<package version="3.0" xmlns="http://www.idpf.org/2007/opf">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test Book</dc:title>
  </metadata>
</package>""")
    
    return epub_path


@pytest.fixture
def invalid_epub_mimetype(tmp_path):
    """
    Create an EPUB with invalid mimetype.
    """
    epub_path = tmp_path / "invalid_mimetype.epub"
    
    with zipfile.ZipFile(epub_path, 'w') as zf:
        zf.writestr("mimetype", "application/pdf")  # Wrong mimetype
    
    return epub_path


@pytest.fixture
def invalid_epub_no_mimetype(tmp_path):
    """
    Create an EPUB without mimetype file.
    """
    epub_path = tmp_path / "no_mimetype.epub"
    
    with zipfile.ZipFile(epub_path, 'w') as zf:
        zf.writestr("content.txt", "Some content")
    
    return epub_path


@pytest.fixture
def corrupted_file(tmp_path):
    """
    Create a corrupted (non-ZIP) file with .epub extension.
    """
    epub_path = tmp_path / "corrupted.epub"
    epub_path.write_text("This is not a ZIP file")
    return epub_path


@pytest.fixture
def db_with_books(temp_db, sample_books):
    """
    Create a database pre-populated with sample books.
    """
    import database as db
    db.insert_books(sample_books)
    return temp_db
