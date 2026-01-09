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
from operations import IndexOperation

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

    def build_index(self, max_pages: int = None, resume: bool = True) -> int:
        """
        Build the complete index by scraping all book pages (from scratch).

        Supports checkpoint/resume: if interrupted, can continue from last checkpoint.

        Args:
            max_pages: Maximum pages to scrape (None = all pages)
            resume: If True, try to resume an existing operation

        Returns:
            Total number of books indexed
        """
        operation = None
        start_page = 1
        total_books = 0
        is_resuming = False

        # Try to resume existing operation
        if resume:
            try:
                operation = IndexOperation.get_resumable_build()
                if operation:
                    checkpoint = operation.get_checkpoint()
                    start_page = checkpoint.get('current_page', 1)
                    self.books_buffer = checkpoint.get('books_buffer', [])
                    total_books = checkpoint.get('total_books_scraped', 0)
                    is_resuming = True
                    console.print(f"\n[bold yellow]⏯️  Reanudando desde página {start_page}...[/bold yellow]")
                    console.print(f"[dim]Libros ya indexados: {total_books}[/dim]\n")
            except Exception as e:
                logger.warning(f"Error al intentar reanudar: {e}")
                operation = None

        if not operation:
            console.print("\n[bold cyan]🔁 Reconstruyendo índice desde cero...[/bold cyan]")
            console.print(f"[dim]Fuente: {settings.LECTULANDIA_BASE_URL}/book/[/dim]\n")

            # Initialize database and clear existing data
            db.init_db()
            self.books_buffer = []

            # Create new operation
            try:
                operation = IndexOperation.create_build(max_pages)
            except Exception as e:
                logger.warning(f"Error creando operación, continuando sin tracking: {e}")
                operation = None

        page = start_page
        has_more = True
        checkpoint_interval = 10  # Save checkpoint every N pages
        consecutive_errors = 0

        try:
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
                    books=total_books
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
                        consecutive_errors = 0  # Reset error counter on success

                        # Flush buffer periodically
                        if len(self.books_buffer) >= self.buffer_size:
                            clear_first = not is_resuming and page <= start_page + 1 and total_books == len(page_books)
                            self._flush_buffer(clear_existing=clear_first)

                        progress.update(task, books=total_books)

                        # Save checkpoint periodically
                        if operation and page % checkpoint_interval == 0:
                            operation.save_checkpoint(
                                page=page,
                                books_buffer=self.books_buffer,
                                total_books_scraped=total_books
                            )
                            logger.debug(f"Checkpoint guardado en página {page}")

                        # Check for next page
                        next_link = soup.find("a", class_="next page-numbers")
                        if not next_link:
                            has_more = False
                        else:
                            page += 1
                            smart_delay(0.3, 0.8)  # Be nice to the server

                    except Exception as e:
                        logger.warning(f"Error en página {page}: {e}")
                        consecutive_errors += 1
                        # Try to continue with next page
                        page += 1
                        if consecutive_errors >= 3:  # If we fail on multiple consecutive pages, stop
                            has_more = False
                            if operation:
                                operation.fail(f"Demasiados errores consecutivos: {e}")

            # Flush remaining books
            if self.books_buffer:
                self._flush_buffer()

            # Update metadata
            pages_scraped = page - 1 if not has_more else page
            db.update_metadata("last_updated", datetime.now().isoformat())
            db.update_metadata("total_books", str(db.get_total_books()))
            db.update_metadata("total_pages_scraped", str(pages_scraped))
            db.update_metadata("source_url", f"{settings.LECTULANDIA_BASE_URL}/book/")

            # Mark operation as completed
            if operation and consecutive_errors < 3:
                operation.complete(total_books=db.get_total_books())

            console.print(f"\n[green bold]✅ Índice construido![/green bold]")
            console.print(f"   📚 [cyan]{db.get_total_books()}[/cyan] libros indexados")
            console.print(f"   📄 [cyan]{pages_scraped}[/cyan] páginas procesadas")
            console.print(f"   💾 Guardado en: [dim]{db.DB_FILE}[/dim]\n")

            return db.get_total_books()

        except KeyboardInterrupt:
            # Save checkpoint on interruption
            console.print("\n[yellow]Interrupción detectada, guardando progreso...[/yellow]")
            if self.books_buffer:
                self._flush_buffer()
            if operation:
                operation.save_checkpoint(
                    page=page,
                    books_buffer=self.books_buffer,
                    total_books_scraped=total_books
                )
                console.print(f"[green]✓ Checkpoint guardado en página {page}[/green]")
                console.print(f"[dim]Ejecuta de nuevo para continuar desde este punto.[/dim]\n")
            raise

    def _flush_buffer(self, clear_existing: bool = False) -> None:
        """Flush the books buffer to the database."""
        if self.books_buffer:
            db.insert_books(self.books_buffer, clear_existing=clear_existing)
            self.books_buffer = []

    def update_index(self, max_pages: int = 10, resume: bool = True) -> int:
        """
        Update the index incrementally by adding only new books.

        Scrapes exactly max_pages pages from page 1, adding any new books found.
        Supports checkpoint/resume for interrupted operations.

        Args:
            max_pages: Number of pages to check (default 10)
            resume: If True, try to resume an existing operation

        Returns:
            Number of new books added
        """
        # Check if database exists
        if not db.is_available():
            console.print("[yellow]No existe índice previo. Construyendo desde cero...[/yellow]")
            return self.build_index()

        operation = None
        start_page = 1
        new_books = []
        is_resuming = False

        # Try to resume existing operation
        if resume:
            try:
                operation = IndexOperation.get_resumable_update()
                if operation:
                    checkpoint = operation.get_checkpoint()
                    start_page = checkpoint.get('current_page', 1)
                    new_books = checkpoint.get('new_books', [])
                    is_resuming = True
                    console.print(f"\n[bold yellow]⏯️  Reanudando actualización desde página {start_page}...[/bold yellow]")
                    console.print(f"[dim]Libros nuevos encontrados: {len(new_books)}[/dim]\n")
            except Exception as e:
                logger.warning(f"Error al intentar reanudar: {e}")
                operation = None

        if not operation:
            # Create new operation
            try:
                operation = IndexOperation.create_update(max_pages)
            except Exception as e:
                logger.warning(f"Error creando operación, continuando sin tracking: {e}")
                operation = None

        # Get existing slugs for fast lookup
        existing_slugs = db.get_existing_slugs()
        existing_count = len(existing_slugs)

        if not is_resuming:
            console.print("\n[bold cyan]🔄 Actualizando índice (solo libros nuevos)...[/bold cyan]")
            console.print(f"[dim]Índice actual: {existing_count} libros[/dim]")
            console.print(f"[dim]Páginas a revisar: {max_pages}[/dim]\n")

        page = start_page
        checkpoint_interval = 5  # Save checkpoint every N pages

        try:
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
                    new_count=len(new_books)
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

                        # Save checkpoint periodically
                        if operation and page % checkpoint_interval == 0:
                            checkpoint_data = operation.checkpoint_data.copy()
                            checkpoint_data['current_page'] = page
                            checkpoint_data['new_books'] = new_books
                            checkpoint_data['new_books_found'] = len(new_books)
                            operation.save_checkpoint(
                                page=page,
                                total_books_scraped=len(new_books)
                            )
                            logger.debug(f"Checkpoint guardado en página {page}")

                        # Check for next page
                        next_link = soup.find("a", class_="next page-numbers")
                        if not next_link:
                            console.print(f"\n[dim]No hay más páginas disponibles.[/dim]")
                            break

                        page += 1
                        smart_delay(0.3, 0.8)

                    except Exception as e:
                        logger.warning(f"Error en página {page}: {e}")
                        if operation:
                            operation.fail(str(e))
                        break

                progress.update(task, completed=max_pages)

            if not new_books:
                console.print("\n[green]✓ El índice ya está actualizado. No hay libros nuevos.[/green]\n")
                if operation:
                    operation.complete(total_books=0)
                return 0

            # Insert new books
            inserted = db.insert_books(new_books)

            # Update metadata
            db.update_metadata("last_updated", datetime.now().isoformat())
            db.update_metadata("total_books", str(db.get_total_books()))
            db.update_metadata("pages_checked_for_update", str(page))

            # Mark operation as completed
            if operation:
                operation.complete(total_books=inserted)

            console.print(f"\n[green bold]✅ Índice actualizado![/green bold]")
            console.print(f"   [green]+{inserted}[/green] libros nuevos añadidos")
            console.print(f"   📚 [cyan]{db.get_total_books()}[/cyan] libros en total\n")

            return inserted

        except KeyboardInterrupt:
            # Save checkpoint on interruption
            console.print("\n[yellow]Interrupción detectada, guardando progreso...[/yellow]")
            if operation:
                checkpoint_data = operation.checkpoint_data.copy()
                checkpoint_data['current_page'] = page
                checkpoint_data['new_books'] = new_books
                checkpoint_data['new_books_found'] = len(new_books)
                operation.save_checkpoint(
                    page=page,
                    total_books_scraped=len(new_books)
                )
                console.print(f"[green]✓ Checkpoint guardado en página {page}[/green]")
                console.print(f"[dim]Ejecuta de nuevo para continuar desde este punto.[/dim]\n")
            raise

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


def rebuild_index(max_pages: int = None, resume: bool = True) -> None:
    """
    Rebuild the entire index from scratch.

    Args:
        max_pages: Maximum pages to scrape (None = all pages)
        resume: If True, try to resume an existing operation
    """
    indexer = LectulandiaIndexer()
    try:
        indexer.build_index(max_pages=max_pages, resume=resume)
    finally:
        indexer.close()


def update_index(max_pages: int = 10, resume: bool = True) -> None:
    """
    Update the index incrementally (only new books).

    Args:
        max_pages: Maximum pages to check
        resume: If True, try to resume an existing operation
    """
    indexer = LectulandiaIndexer()
    try:
        indexer.update_index(max_pages=max_pages, resume=resume)
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
