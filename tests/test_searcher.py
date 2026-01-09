"""
Tests for the searcher module (BookSearcher).
"""

import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


class TestBookSearcherAvailability:
    """Tests for searcher availability checks."""
    
    def test_not_available_empty_db(self, temp_db):
        """is_available should return False for empty database."""
        from searcher import BookSearcher
        
        searcher = BookSearcher()
        assert searcher.is_available() is False
    
    def test_available_with_books(self, db_with_books):
        """is_available should return True when database has books."""
        from searcher import BookSearcher
        
        searcher = BookSearcher()
        assert searcher.is_available() is True


class TestBookSearcherSearch:
    """Tests for search functionality."""
    
    def test_search_returns_results(self, db_with_books):
        """search should return matching books."""
        from searcher import BookSearcher
        
        searcher = BookSearcher()
        results = searcher.search("soledad", limit=10)
        
        assert len(results) >= 1
        assert any("Soledad" in r["title"] for r in results)
    
    def test_search_by_title(self, db_with_books):
        """search with search_by='title' should search only titles."""
        from searcher import BookSearcher
        
        searcher = BookSearcher()
        results = searcher.search("rayuela", search_by="title", limit=10)
        
        assert len(results) >= 1
        assert results[0]["title"] == "Rayuela"
    
    def test_search_by_author(self, db_with_books):
        """search with search_by='author' should search only authors."""
        from searcher import BookSearcher
        
        searcher = BookSearcher()
        results = searcher.search("cortazar", search_by="author", limit=10)
        
        assert len(results) >= 1
        assert "Cortázar" in results[0]["author"]
    
    def test_search_by_all(self, db_with_books):
        """search with search_by='all' should match title or author."""
        from searcher import BookSearcher
        
        searcher = BookSearcher()
        
        # Search for author name
        results = searcher.search("allende", search_by="all", limit=10)
        
        assert len(results) >= 1
        # Should find Isabel Allende's book
        assert any("Allende" in r["author"] for r in results)
    
    def test_search_empty_query(self, db_with_books):
        """Empty query should return empty list."""
        from searcher import BookSearcher
        
        searcher = BookSearcher()
        results = searcher.search("", limit=10)
        
        assert results == []
    
    def test_search_no_results(self, db_with_books):
        """Query with no matches should return empty list."""
        from searcher import BookSearcher
        
        searcher = BookSearcher()
        results = searcher.search("xyznonexistentbook", limit=10)
        
        assert results == []
    
    def test_search_respects_limit(self, db_with_books):
        """search should respect the limit parameter."""
        from searcher import BookSearcher
        
        searcher = BookSearcher()
        
        # Search for common term that matches multiple books
        results = searcher.search("garcia", limit=2)
        
        assert len(results) <= 2
    
    def test_search_results_have_score(self, db_with_books):
        """Results should include a score field."""
        from searcher import BookSearcher
        
        searcher = BookSearcher()
        results = searcher.search("cien anos", limit=5)
        
        assert len(results) >= 1
        assert "score" in results[0]
        assert isinstance(results[0]["score"], int)
    
    def test_search_not_available_returns_empty(self, temp_db):
        """search on empty database should return empty list."""
        from searcher import BookSearcher
        
        searcher = BookSearcher()
        results = searcher.search("anything")
        
        assert results == []


class TestBookSearcherGetBooksByAuthor:
    """Tests for get_books_by_author method."""
    
    def test_get_books_by_author(self, db_with_books):
        """get_books_by_author should return books by the specified author."""
        from searcher import BookSearcher
        
        searcher = BookSearcher()
        results = searcher.get_books_by_author("García Márquez")
        
        assert len(results) >= 1
        assert all("García Márquez" in r["author"] for r in results)
    
    def test_get_books_by_author_sorted(self, db_with_books):
        """Results should be sorted alphabetically by title."""
        from searcher import BookSearcher
        
        searcher = BookSearcher()
        results = searcher.get_books_by_author("García Márquez")
        
        if len(results) > 1:
            titles = [r["title"] for r in results]
            assert titles == sorted(titles)


class TestBookSearcherIndexInfo:
    """Tests for index info retrieval."""
    
    def test_get_index_info_with_data(self, db_with_books, sample_books):
        """get_index_info should return metadata."""
        import database as db
        from searcher import BookSearcher
        
        # Set metadata
        db.update_metadata("last_updated", "2026-01-09T10:00:00")
        db.update_metadata("total_books", str(len(sample_books)))
        db.update_metadata("source_url", "https://ww3.lectulandia.com/book/")
        
        searcher = BookSearcher()
        info = searcher.get_index_info()
        
        assert info is not None
        assert info["last_updated"] == "2026-01-09T10:00:00"
        assert info["total_books"] == len(sample_books)
    
    def test_get_index_info_empty_db(self, temp_db):
        """get_index_info should return None for empty database."""
        from searcher import BookSearcher
        
        searcher = BookSearcher()
        info = searcher.get_index_info()
        
        assert info is None


class TestBookSearcherRandomBooks:
    """Tests for random book retrieval."""
    
    def test_get_random_books(self, db_with_books):
        """get_random_books should return requested number of books."""
        from searcher import BookSearcher
        
        searcher = BookSearcher()
        random_books = searcher.get_random_books(3)
        
        assert len(random_books) == 3
        assert all("title" in book for book in random_books)
    
    def test_get_random_books_less_than_available(self, db_with_books, sample_books):
        """Should return all books if count exceeds total."""
        from searcher import BookSearcher
        
        searcher = BookSearcher()
        random_books = searcher.get_random_books(100)  # More than we have
        
        # Should return all available books
        assert len(random_books) == len(sample_books)


class TestDisplaySearchResults:
    """Tests for display_search_results function."""
    
    def test_display_search_results_with_results(self, db_with_books, capsys):
        """display_search_results should print a table with results."""
        from searcher import display_search_results
        
        results = [
            {"title": "Test Book", "author": "Test Author", "score": 85},
        ]
        
        display_search_results(results, "test query")
        
        captured = capsys.readouterr()
        assert "Test Book" in captured.out or "test query" in captured.out
    
    def test_display_search_results_no_results(self, capsys):
        """display_search_results should show message when no results."""
        from searcher import display_search_results
        
        display_search_results([], "nonexistent")
        
        captured = capsys.readouterr()
        assert "No se encontraron" in captured.out or "nonexistent" in captured.out
