"""
Indexer module for building a local catalog of Lectulandia books.

This module scrapes the website to build a JSON index that can be used
for fast local searches without making HTTP requests.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TaskProgressColumn, TimeElapsedColumn

from src.infrastructure.http.http_client import HTTPClient
from src.utils.delays import smart_delay
from config.settings import settings

console = Console()

# Default index file path
INDEX_DIR = Path(__file__).parent.parent / "data"
INDEX_FILE = INDEX_DIR / "catalog_index.json"


class LectulandiaIndexer:
    """
    Builds and maintains a local index of Lectulandia's catalog.

    Scrapes all books from /book/ pages with pagination support.
    """

    def __init__(self, proxy: str = None):
        self.http_client = HTTPClient(proxy=proxy)
        self.index = {
            "metadata": {
                "last_updated": None,
                "total_books": 0,
                "source_url": f"{settings.LECTULANDIA_BASE_URL}/book/",
            },
            "books": [],
        }

    def build_index(self, max_pages: int = None) -> dict:
        """
        Build the complete index by scraping all book pages (from scratch).

        Args:
            max_pages: Maximum pages to scrape (None = all pages)

        Returns:
            The built index dictionary
        """
        console.print("\n[bold cyan]🔁 Reconstruyendo índice desde cero...[/bold cyan]")
        console.print(f"[dim]Fuente: {settings.LECTULANDIA_BASE_URL}/book/[/dim]\n")

        books = []
        page = 1
        has_more = True

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

                    books.extend(page_books)
                    progress.update(task, books=len(books))

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

        # Store books in index
        self.index["books"] = books
        self.index["metadata"]["last_updated"] = datetime.now().isoformat()
        self.index["metadata"]["total_books"] = len(books)
        self.index["metadata"]["total_pages_scraped"] = page - 1 if not has_more else page

        console.print(f"\n[green bold]✅ Índice construido![/green bold]")
        console.print(f"   📚 [cyan]{len(books)}[/cyan] libros indexados")
        console.print(f"   📄 [cyan]{self.index['metadata']['total_pages_scraped']}[/cyan] páginas procesadas\n")

        return self.index

    def update_index(self, max_pages: int = 10) -> dict:
        """
        Update the index incrementally by adding only new books.

        Scrapes exactly max_pages pages from page 1, adding any new books found.

        Args:
            max_pages: Number of pages to check (default 10)

        Returns:
            The updated index dictionary
        """
        # Load existing index
        existing_index = self.load_index()

        if not existing_index or not existing_index.get("books"):
            console.print("[yellow]No existe índice previo. Construyendo desde cero...[/yellow]")
            return self.build_index()

        # Build set of existing slugs for fast lookup
        existing_slugs = {book["slug"] for book in existing_index["books"]}
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
            return existing_index

        # Prepend new books to existing list
        self.index["books"] = new_books + existing_index["books"]
        self.index["metadata"]["last_updated"] = datetime.now().isoformat()
        self.index["metadata"]["total_books"] = len(self.index["books"])
        self.index["metadata"]["pages_checked_for_update"] = page

        console.print(f"\n[green bold]✅ Índice actualizado![/green bold]")
        console.print(f"   [green]+{len(new_books)}[/green] libros nuevos añadidos")
        console.print(f"   📚 [cyan]{len(self.index['books'])}[/cyan] libros en total\n")

        return self.index

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

    def save_index(self, filepath: Path = None) -> None:
        """Save the index to a JSON file."""
        if filepath is None:
            filepath = INDEX_FILE

        # Ensure directory exists
        filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.index, f, ensure_ascii=False, indent=2)

        console.print(f"[green]✓[/green] Índice guardado en: [dim]{filepath}[/dim]\n")

    def load_index(self, filepath: Path = None) -> dict:
        """Load an existing index from file."""
        if filepath is None:
            filepath = INDEX_FILE

        if not filepath.exists():
            return None

        with open(filepath, "r", encoding="utf-8") as f:
            self.index = json.load(f)

        return self.index

    def close(self):
        """Close HTTP client."""
        if hasattr(self, 'http_client'):
            self.http_client.close()

    def __del__(self):
        """Cleanup."""
        self.close()


def get_index_info() -> dict | None:
    """Get information about the existing index."""
    if not INDEX_FILE.exists():
        return None

    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            index = json.load(f)
        return index.get("metadata")
    except Exception:
        return None


def rebuild_index(max_pages: int = None) -> None:
    """
    Rebuild the entire index from scratch.

    Args:
        max_pages: Maximum pages to scrape (None = all pages)
    """
    indexer = LectulandiaIndexer()
    try:
        indexer.build_index(max_pages=max_pages)
        indexer.save_index()
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
        indexer.save_index()
    finally:
        indexer.close()


if __name__ == "__main__":
    # Quick test / manual rebuild
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--update":
        update_index()
    else:
        max_pages = int(sys.argv[1]) if len(sys.argv) > 1 else 10
        rebuild_index(max_pages=max_pages)
