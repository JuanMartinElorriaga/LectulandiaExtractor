"""
Searcher module for fast local catalog searches.

Uses fuzzy matching to find books in the local index without
making HTTP requests to the website.
"""

import json
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz, process
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()

# Index file path
INDEX_FILE = Path(__file__).parent.parent / "data" / "catalog_index.json"


class BookSearcher:
    """
    Fast fuzzy search engine for the local book catalog.

    Features:
    - Fuzzy title search
    - Genre filtering
    - Configurable result limits
    """

    def __init__(self):
        self.index = None
        self._load_index()

    def _load_index(self) -> bool:
        """Load the index from file."""
        if not INDEX_FILE.exists():
            return False

        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            self.index = json.load(f)

        return True

    def is_available(self) -> bool:
        """Check if the index is loaded and available."""
        return self.index is not None and len(self.index.get("books", [])) > 0

    def get_index_info(self) -> Optional[dict]:
        """Get metadata about the current index."""
        if not self.index:
            return None
        return self.index.get("metadata")

    def search(
        self,
        query: str,
        search_by: str = "all",
        limit: int = 20,
        min_score: int = 60,
    ) -> list[dict]:
        """
        Search for books by title, author, or both using fuzzy matching.
        
        Args:
            query: Search query string
            search_by: "title", "author", or "all" (default)
            limit: Maximum number of results
            min_score: Minimum fuzzy match score (0-100)
            
        Returns:
            List of matching books with scores
        """
        if not self.is_available():
            return []
        
        books = self.index["books"]
        
        if not books:
            return []
        
        # Create search strings based on search_by parameter
        if search_by == "title":
            search_strings = [book.get('title', '') for book in books]
        elif search_by == "author":
            search_strings = [book.get('author', '') for book in books]
        else:  # "all"
            search_strings = [
                f"{book.get('title', '')} {book.get('author', '')}" 
                for book in books
            ]
        
        # Fuzzy search
        matches = process.extract(
            query,
            search_strings,
            scorer=fuzz.WRatio,
            limit=limit * 2  # Get more to filter by score
        )
        
        results = []
        seen_slugs = set()
        
        for _, score, idx in matches:
            if score >= min_score:
                book = books[idx]
                # Avoid duplicates
                if book["slug"] not in seen_slugs:
                    seen_slugs.add(book["slug"])
                    book_copy = book.copy()
                    book_copy["score"] = score
                    results.append(book_copy)
        
        # Sort by score and limit
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
    
    def get_books_by_author(self, author_name: str, limit: int = 50) -> list[dict]:
        """
        Get all books by a specific author.
        
        Args:
            author_name: Author name to search for
            limit: Maximum number of results
            
        Returns:
            List of books by the author
        """
        results = self.search(author_name, search_by="author", limit=limit, min_score=70)
        # Sort alphabetically by title for author listings
        results.sort(key=lambda x: x.get("title", ""))
        return results

    def get_random_books(self, count: int = 10) -> list[dict]:
        """Get random books from the index."""
        import random

        if not self.is_available():
            return []

        books = self.index["books"]
        return random.sample(books, min(count, len(books)))


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

