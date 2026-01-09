"""
Tests for the database module (SQLite + FTS5).
"""

import sqlite3
import pytest


class TestInitDb:
    """Tests for database initialization."""
    
    def test_init_db_creates_tables(self, temp_db):
        """Verify that init_db creates all required tables."""
        import database as db
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Check books table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='books'"
        )
        assert cursor.fetchone() is not None, "books table should exist"
        
        # Check books_fts virtual table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='books_fts'"
        )
        assert cursor.fetchone() is not None, "books_fts table should exist"
        
        # Check metadata table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='metadata'"
        )
        assert cursor.fetchone() is not None, "metadata table should exist"
        
        conn.close()
    
    def test_init_db_creates_index(self, temp_db):
        """Verify that init_db creates the slug index."""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_books_slug'"
        )
        assert cursor.fetchone() is not None, "idx_books_slug index should exist"
        
        conn.close()
    
    def test_init_db_idempotent(self, temp_db):
        """Calling init_db multiple times should not raise errors."""
        import database as db
        
        # Should not raise
        db.init_db()
        db.init_db()
        db.init_db()


class TestInsertBooks:
    """Tests for inserting books."""
    
    def test_insert_books_basic(self, temp_db, sample_books):
        """Insert books and verify count."""
        import database as db
        
        inserted = db.insert_books(sample_books)
        
        assert inserted == len(sample_books)
        assert db.get_total_books() == len(sample_books)
    
    def test_insert_books_duplicates_ignored(self, temp_db, sample_books):
        """Duplicate slugs should be ignored (OR IGNORE)."""
        import database as db
        
        # Insert once
        first_insert = db.insert_books(sample_books)
        
        # Insert again - duplicates should be ignored
        second_insert = db.insert_books(sample_books)
        
        assert first_insert == len(sample_books)
        assert second_insert == 0  # All duplicates, nothing new inserted
        assert db.get_total_books() == len(sample_books)
    
    def test_insert_books_missing_author(self, temp_db, sample_books_no_author):
        """Books without author should default to 'Desconocido'."""
        import database as db
        
        db.insert_books(sample_books_no_author)
        
        book = db.get_book_by_slug("libro-sin-autor")
        assert book is not None
        assert book["author"] == "Desconocido"
    
    def test_insert_books_clear_existing(self, temp_db, sample_books):
        """clear_existing=True should delete all existing books first."""
        import database as db
        
        # Insert initial books
        db.insert_books(sample_books)
        assert db.get_total_books() == 5
        
        # Insert new books with clear_existing
        new_books = [{"title": "New Book", "author": "New Author", "slug": "new-book", "url": "https://example.com"}]
        db.insert_books(new_books, clear_existing=True)
        
        assert db.get_total_books() == 1
        assert db.get_book_by_slug("new-book") is not None
        assert db.get_book_by_slug("cien-anos-de-soledad") is None


class TestSearchBooks:
    """Tests for FTS5 search functionality."""
    
    def test_search_books_by_title(self, db_with_books):
        """Search by title should find matching books."""
        import database as db
        
        results = db.search_books("cien anos", search_by="title", limit=10)
        
        assert len(results) >= 1
        assert any("Cien Anos" in r["title"] for r in results)
    
    def test_search_books_by_author(self, db_with_books):
        """Search by author should find books by that author."""
        import database as db
        
        results = db.search_books("garcia marquez", search_by="author", limit=10)
        
        assert len(results) >= 1
        assert all("García Márquez" in r["author"] for r in results)
    
    def test_search_books_all(self, db_with_books):
        """Search 'all' should match title or author."""
        import database as db
        
        # Search for author name
        results = db.search_books("cortazar", search_by="all", limit=10)
        
        assert len(results) >= 1
        assert any("Cortázar" in r["author"] for r in results)
    
    def test_search_books_case_insensitive(self, db_with_books):
        """Search should be case-insensitive."""
        import database as db
        
        results_lower = db.search_books("garcia", search_by="author", limit=10)
        results_upper = db.search_books("GARCIA", search_by="author", limit=10)
        results_mixed = db.search_books("GaRcIa", search_by="author", limit=10)
        
        assert len(results_lower) == len(results_upper) == len(results_mixed)
        assert len(results_lower) >= 1
    
    def test_search_books_partial_match(self, db_with_books):
        """Partial terms should match via prefix search."""
        import database as db
        
        results = db.search_books("ray", search_by="title", limit=10)
        
        assert len(results) >= 1
        assert any("Rayuela" in r["title"] for r in results)
    
    def test_search_books_no_results(self, db_with_books):
        """Search with no matches should return empty list."""
        import database as db
        
        results = db.search_books("xyznonexistent", search_by="all", limit=10)
        
        assert results == []
    
    def test_search_books_empty_query(self, db_with_books):
        """Empty query should return empty list."""
        import database as db
        
        results = db.search_books("", search_by="all", limit=10)
        
        assert results == []
    
    def test_search_books_returns_score(self, db_with_books):
        """Results should include a score field."""
        import database as db
        
        results = db.search_books("soledad", search_by="title", limit=10)
        
        assert len(results) >= 1
        assert "score" in results[0]
        assert isinstance(results[0]["score"], int)
        assert 0 <= results[0]["score"] <= 100


class TestMetadata:
    """Tests for metadata operations."""
    
    def test_update_and_get_metadata(self, temp_db):
        """Update and retrieve metadata."""
        import database as db
        
        db.update_metadata("last_updated", "2026-01-09")
        db.update_metadata("total_books", "1000")
        
        metadata = db.get_metadata()
        
        assert metadata["last_updated"] == "2026-01-09"
        assert metadata["total_books"] == "1000"
    
    def test_update_metadata_overwrites(self, temp_db):
        """Updating same key should overwrite value."""
        import database as db
        
        db.update_metadata("version", "1.0")
        db.update_metadata("version", "2.0")
        
        metadata = db.get_metadata()
        assert metadata["version"] == "2.0"


class TestUtilityFunctions:
    """Tests for utility functions."""
    
    def test_get_total_books(self, db_with_books, sample_books):
        """get_total_books should return correct count."""
        import database as db
        
        assert db.get_total_books() == len(sample_books)
    
    def test_get_total_books_empty_db(self, temp_db):
        """get_total_books should return 0 for empty database."""
        import database as db
        
        assert db.get_total_books() == 0
    
    def test_get_book_by_slug(self, db_with_books):
        """get_book_by_slug should return the correct book."""
        import database as db
        
        book = db.get_book_by_slug("rayuela")
        
        assert book is not None
        assert book["title"] == "Rayuela"
        assert book["author"] == "Julio Cortázar"
    
    def test_get_book_by_slug_not_found(self, db_with_books):
        """get_book_by_slug should return None for non-existent slug."""
        import database as db
        
        book = db.get_book_by_slug("nonexistent-book")
        
        assert book is None
    
    def test_slug_exists(self, db_with_books):
        """slug_exists should return True for existing slugs."""
        import database as db
        
        assert db.slug_exists("rayuela") is True
        assert db.slug_exists("nonexistent") is False
    
    def test_get_existing_slugs(self, db_with_books, sample_books):
        """get_existing_slugs should return set of all slugs."""
        import database as db
        
        slugs = db.get_existing_slugs()
        
        assert isinstance(slugs, set)
        assert len(slugs) == len(sample_books)
        assert "rayuela" in slugs
        assert "cien-anos-de-soledad" in slugs
    
    def test_is_available(self, db_with_books):
        """is_available should return True when DB has books."""
        import database as db
        
        assert db.is_available() is True
    
    def test_is_available_empty_db(self, temp_db):
        """is_available should return False for empty database."""
        import database as db
        
        assert db.is_available() is False
    
    def test_get_random_books(self, db_with_books):
        """get_random_books should return requested number of books."""
        import database as db
        
        random_books = db.get_random_books(3)
        
        assert len(random_books) == 3
        assert all("title" in book for book in random_books)
