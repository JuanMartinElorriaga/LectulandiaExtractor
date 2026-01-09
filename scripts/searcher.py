"""
Searcher module for fast local catalog searches.

Uses SQLite FTS5 full-text search for fast queries without
loading the entire catalog into memory.
"""

from typing import Optional

from rich.console import Console
from rich.table import Table
from rich import box

# Import database module
import database as db

console = Console()


class BookSearcher:
    """
    Fast search engine for the local book catalog using SQLite FTS5.

    Features:
    - Fast full-text search on title and author
    - No memory overhead (queries database directly)
    - Configurable result limits
    """

    def __init__(self):
        pass  # No need to load anything into memory

    def is_available(self) -> bool:
        """Check if the database is available."""
        return db.is_available()

    def get_index_info(self) -> Optional[dict]:
        """Get metadata about the current index."""
        if not self.is_available():
            return None
        
        metadata = db.get_metadata()
        if not metadata:
            return None
        
        return {
            "last_updated": metadata.get("last_updated"),
            "total_books": int(metadata.get("total_books", 0)),
            "total_pages_scraped": int(metadata.get("total_pages_scraped", 0)),
            "source_url": metadata.get("source_url"),
        }

    def search(
        self,
        query: str,
        search_by: str = "all",
        limit: int = 20,
        min_score: int = 0,
    ) -> list[dict]:
        """
        Search for books by title, author, or both using FTS5.

        Args:
            query: Search query string
            search_by: "title", "author", or "all" (default)
            limit: Maximum number of results
            min_score: Minimum match score (0-100) - used for filtering

        Returns:
            List of matching books with scores
        """
        if not self.is_available():
            return []

        results = db.search_books(query, search_by=search_by, limit=limit)
        
        # Filter by min_score
        return [r for r in results if r.get("score", 0) >= min_score]

    def get_books_by_author(self, author_name: str, limit: int = 50) -> list[dict]:
        """
        Get all books by a specific author.

        Args:
            author_name: Author name to search for
            limit: Maximum number of results

        Returns:
            List of books by the author
        """
        results = self.search(author_name, search_by="author", limit=limit, min_score=50)
        # Sort alphabetically by title for author listings
        results.sort(key=lambda x: x.get("title", ""))
        return results

    def get_random_books(self, count: int = 10) -> list[dict]:
        """Get random books from the catalog."""
        return db.get_random_books(count)
    
    def get_book_by_slug(self, slug: str) -> Optional[dict]:
        """Get a single book by its slug."""
        return db.get_book_by_slug(slug)


def display_search_results(results: list[dict], query: str) -> None:
    """Display search results in a styled table."""
    if not results:
        console.print(f"\n[yellow]No se encontraron resultados para '{query}'[/yellow]\n")
        return

    table = Table(
        title=f"[bold]Resultados para: '{query}'[/bold]",
        box=box.ROUNDED,
        show_lines=False,
        header_style="bold magenta",
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Título", style="cyan", max_width=45)
    table.add_column("Autor", style="yellow", max_width=25)
    table.add_column("Match", justify="right", style="green", width=6)

    for i, book in enumerate(results, 1):
        score = f"{book.get('score', 0)}%"
        author = book.get("author", "—")
        table.add_row(str(i), book["title"], author, score)

    console.print()
    console.print(table)
    console.print()


def quick_search(query: str) -> list[dict]:
    """Quick search function for CLI integration."""
    searcher = BookSearcher()

    if not searcher.is_available():
        console.print("[yellow]⚠️  El índice no está disponible. Ejecuta 'Actualizar índice' primero.[/yellow]")
        return []

    results = searcher.search(query)
    display_search_results(results, query)
    return results


if __name__ == "__main__":
    # Quick test
    import sys

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        quick_search(query)
    else:
        print("Uso: python searcher.py <búsqueda>")
