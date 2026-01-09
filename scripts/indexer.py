"""
Indexer module for building a local catalog of Lectulandia books.

This module scrapes the website to build a SQLite database index that can be used
for fast local searches without making HTTP requests.
"""

import json
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TaskProgressColumn, TimeElapsedColumn

from src.infrastructure.http.http_client import HTTPClient
from src.utils.delays import smart_delay
from config.settings import settings

# Import database module
import database as db

console = Console()

# Legacy JSON file path (for migration)
INDEX_DIR = Path(__file__).parent.parent / "data"
INDEX_FILE = INDEX_DIR / "catalog_index.json"


class LectulandiaIndexer:
    """
    Builds and maintains a local index of Lectulandia's catalog.

    Scrapes all books from /book/ pages with pagination support.
    Stores data in SQLite with FTS5 for fast searching.
    """

    def __init__(self, proxy: str = None):
        self.http_client = HTTPClient(proxy=proxy)
        self.books_buffer = []  # Buffer for batch inserts
        self.buffer_size = 100  # Flush every N books

    def build_index(self, max_pages: int = None) -> int:
        """
        Build the complete index by scraping all book pages (from scratch).

        Args:
            max_pages: Maximum pages to scrape (None = all pages)

        Returns:
            Total number of books indexed
        """
        console.print("\n[bold cyan]🔁 Reconstruyendo índice desde cero...[/bold cyan]")
        console.print(f"[dim]Fuente: {settings.LECTULANDIA_BASE_URL}/book/[/dim]\n")

        # Initialize database and clear existing data
        db.init_db()
        
        total_books = 0
        page = 1
        has_more = True
        self.books_buffer = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=30),
            TextColumn("[cyan]{task.fields[books]}[/cyan] libros"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Indexando",
                total=None,  # Unknown total
                books=0
            )

            while has_more:
                # Check max pages limit
                if max_pages and page > max_pages:
                    console.print(f"\n[dim]Límite de {max_pages} páginas alcanzado.[/dim]")
                    break

                progress.update(task, description=f"Página {page}")

                try:
                    # Build URL for current page
                    if page == 1:
                        url = f"{settings.LECTULANDIA_BASE_URL}/book/"
                    else:
                        url = f"{settings.LECTULANDIA_BASE_URL}/book/page/{page}/"

                    # Fetch page
                    soup = self.http_client.get_soup(url)

                    # Extract books from this page
                    page_books = self._extract_books_from_page(soup)

                    if not page_books:
                        # No more books, we've reached the end
                        has_more = False
                        continue

                    # Add to buffer
                    self.books_buffer.extend(page_books)
                    total_books += len(page_books)
                    
                    # Flush buffer periodically
                    if len(self.books_buffer) >= self.buffer_size:
                        self._flush_buffer(clear_existing=(page == 1 and total_books == len(page_books)))
                    
                    progress.update(task, books=total_books)

                    # Check for next page
                    next_link = soup.find("a", class_="next page-numbers")
                    if not next_link:
                        has_more = False
                    else:
                        page += 1
                        smart_delay(0.3, 0.8)  # Be nice to the server

                except Exception as e:
                    logger.warning(f"Error en página {page}: {e}")
                    # Try to continue with next page
                    page += 1
                    if page > 3:  # If we fail on multiple pages, stop
                        has_more = False

        # Flush remaining books
        if self.books_buffer:
            self._flush_buffer()

        # Update metadata
        pages_scraped = page - 1 if not has_more else page
        db.update_metadata("last_updated", datetime.now().isoformat())
        db.update_metadata("total_books", str(db.get_total_books()))
        db.update_metadata("total_pages_scraped", str(pages_scraped))
        db.update_metadata("source_url", f"{settings.LECTULANDIA_BASE_URL}/book/")

        console.print(f"\n[green bold]✅ Índice construido![/green bold]")
        console.print(f"   📚 [cyan]{db.get_total_books()}[/cyan] libros indexados")
        console.print(f"   📄 [cyan]{pages_scraped}[/cyan] páginas procesadas")
        console.print(f"   💾 Guardado en: [dim]{db.DB_FILE}[/dim]\n")

        return db.get_total_books()

    def _flush_buffer(self, clear_existing: bool = False) -> None:
        """Flush the books buffer to the database."""
        if self.books_buffer:
            db.insert_books(self.books_buffer, clear_existing=clear_existing)
            self.books_buffer = []

    def update_index(self, max_pages: int = 10) -> int:
        """
        Update the index incrementally by adding only new books.

        Scrapes exactly max_pages pages from page 1, adding any new books found.

        Args:
            max_pages: Number of pages to check (default 10)

        Returns:
            Number of new books added
        """
        # Check if database exists
        if not db.is_available():
            console.print("[yellow]No existe índice previo. Construyendo desde cero...[/yellow]")
            return self.build_index()

        # Get existing slugs for fast lookup
        existing_slugs = db.get_existing_slugs()
        existing_count = len(existing_slugs)

        console.print("\n[bold cyan]🔄 Actualizando índice (solo libros nuevos)...[/bold cyan]")
        console.print(f"[dim]Índice actual: {existing_count} libros[/dim]")
        console.print(f"[dim]Páginas a revisar: {max_pages}[/dim]\n")

        new_books = []
        page = 1

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=30),
            TextColumn("[green]+{task.fields[new_count]}[/green] nuevos"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Buscando nuevos",
                total=max_pages,
                new_count=0
            )

            while page <= max_pages:
                progress.update(task, description=f"Página {page}/{max_pages}", completed=page - 1)

                try:
                    # Build URL for current page
                    if page == 1:
                        url = f"{settings.LECTULANDIA_BASE_URL}/book/"
                    else:
                        url = f"{settings.LECTULANDIA_BASE_URL}/book/page/{page}/"

                    # Fetch page
                    soup = self.http_client.get_soup(url)

                    # Extract books from this page
                    page_books = self._extract_books_from_page(soup)

                    if not page_books:
                        # No more books on site
                        console.print(f"\n[dim]No hay más páginas disponibles.[/dim]")
                        break

                    # Check each book on this page
                    for book in page_books:
                        if book["slug"] not in existing_slugs:
                            new_books.append(book)
                            existing_slugs.add(book["slug"])  # Avoid duplicates

                    progress.update(task, new_count=len(new_books))

                    # Check for next page
                    next_link = soup.find("a", class_="next page-numbers")
                    if not next_link:
                        console.print(f"\n[dim]No hay más páginas disponibles.[/dim]")
                        break

                    page += 1
                    smart_delay(0.3, 0.8)

                except Exception as e:
                    logger.warning(f"Error en página {page}: {e}")
                    break

            progress.update(task, completed=max_pages)

        if not new_books:
            console.print("\n[green]✓ El índice ya está actualizado. No hay libros nuevos.[/green]\n")
            return 0

        # Insert new books
        inserted = db.insert_books(new_books)
        
        # Update metadata
        db.update_metadata("last_updated", datetime.now().isoformat())
        db.update_metadata("total_books", str(db.get_total_books()))
        db.update_metadata("pages_checked_for_update", str(page))

        console.print(f"\n[green bold]✅ Índice actualizado![/green bold]")
        console.print(f"   [green]+{inserted}[/green] libros nuevos añadidos")
        console.print(f"   📚 [cyan]{db.get_total_books()}[/cyan] libros en total\n")

        return inserted

    def _extract_books_from_page(self, soup) -> list:
        """Extract book information from a page, including author."""
        books = []

        # Find all book links (original working approach)
        book_links = soup.find_all("a", class_="card-click-target")

        for link in book_links:
            try:
                href = link.get("href", "")
                if not href or "/book/" not in href:
                    continue

                # Extract slug from URL
                slug = href.strip("/").split("/")[-1]

                # Convert slug to readable title
                title = unquote(slug).replace("-", " ").title()

                # Build full URL
                full_url = f"{settings.LECTULANDIA_BASE_URL}{href}"

                # Try to extract author from parent article container
                author = None

                # Navigate up to find parent article
                parent = link.find_parent("article")
                if not parent:
                    parent = link.find_parent("div")

                if parent:
                    # Author is in <a href="/autor/..." rel="tag">Author Name</a>
                    author_link = parent.find("a", href=lambda h: h and "/autor/" in h)
                    if author_link:
                        author = author_link.get_text(strip=True)

                books.append({
                    "title": title,
                    "slug": slug,
                    "url": full_url,
                    "author": author or "Desconocido",
                })

            except Exception as e:
                logger.debug(f"Error extrayendo libro: {e}")
                continue

        return books

    def close(self):
        """Close HTTP client."""
        if hasattr(self, 'http_client'):
            self.http_client.close()

    def __del__(self):
        """Cleanup."""
        self.close()


def get_index_info() -> dict | None:
    """Get information about the existing index."""
    if not db.is_available():
        return None

    metadata = db.get_metadata()
    if not metadata:
        return None
    
    # Convert to expected format
    return {
        "last_updated": metadata.get("last_updated"),
        "total_books": int(metadata.get("total_books", 0)),
        "total_pages_scraped": int(metadata.get("total_pages_scraped", 0)),
        "source_url": metadata.get("source_url"),
    }


def rebuild_index(max_pages: int = None) -> None:
    """
    Rebuild the entire index from scratch.

    Args:
        max_pages: Maximum pages to scrape (None = all pages)
    """
    indexer = LectulandiaIndexer()
    try:
        indexer.build_index(max_pages=max_pages)
    finally:
        indexer.close()


def update_index(max_pages: int = 10) -> None:
    """
    Update the index incrementally (only new books).

    Args:
        max_pages: Maximum pages to check
    """
    indexer = LectulandiaIndexer()
    try:
        indexer.update_index(max_pages=max_pages)
    finally:
        indexer.close()


if __name__ == "__main__":
    # Quick test / manual rebuild
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--update":
        update_index()
    elif len(sys.argv) > 1 and sys.argv[1] == "--migrate":
        count = db.migrate_from_json()
        print(f"Migrated {count} books from JSON to SQLite")
    else:
        max_pages = int(sys.argv[1]) if len(sys.argv) > 1 else 10
        rebuild_index(max_pages=max_pages)
