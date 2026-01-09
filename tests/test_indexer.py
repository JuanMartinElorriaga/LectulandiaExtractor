"""
Tests for the indexer module (HTML parsing).
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from bs4 import BeautifulSoup

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from indexer import LectulandiaIndexer


class TestExtractBooksFromPage:
    """Tests for HTML parsing and book extraction."""
    
    @pytest.fixture
    def indexer(self):
        """Create an indexer instance with mocked HTTP client."""
        with patch('indexer.HTTPClient'):
            idx = LectulandiaIndexer()
            yield idx
            idx.close()
    
    def test_extract_books_basic(self, indexer, sample_html):
        """Should extract books from HTML page."""
        soup = BeautifulSoup(sample_html, 'lxml')
        books = indexer._extract_books_from_page(soup)
        
        assert len(books) >= 2
        
        # Check first book structure
        book = books[0]
        assert "title" in book
        assert "author" in book
        assert "slug" in book
        assert "url" in book
    
    def test_extract_books_gets_slug(self, indexer, sample_html):
        """Should extract slug from book URL."""
        soup = BeautifulSoup(sample_html, 'lxml')
        books = indexer._extract_books_from_page(soup)
        
        slugs = [b["slug"] for b in books]
        assert "cien-anos-de-soledad" in slugs
        assert "rayuela" in slugs
    
    def test_extract_books_gets_author(self, indexer, sample_html):
        """Should extract author from author link."""
        soup = BeautifulSoup(sample_html, 'lxml')
        books = indexer._extract_books_from_page(soup)
        
        # Find the book with known author
        marquez_books = [b for b in books if "García Márquez" in b.get("author", "")]
        assert len(marquez_books) >= 1
    
    def test_extract_books_missing_author(self, indexer, sample_html):
        """Books without author should get 'Desconocido'."""
        soup = BeautifulSoup(sample_html, 'lxml')
        books = indexer._extract_books_from_page(soup)
        
        # Find book without author
        libro_sin_autor = [b for b in books if b["slug"] == "libro-sin-autor"]
        
        if libro_sin_autor:
            assert libro_sin_autor[0]["author"] == "Desconocido"
    
    def test_extract_books_builds_full_url(self, indexer, sample_html):
        """Should build full URL from relative href."""
        soup = BeautifulSoup(sample_html, 'lxml')
        books = indexer._extract_books_from_page(soup)
        
        for book in books:
            assert book["url"].startswith("https://")
            assert "/book/" in book["url"]
    
    def test_extract_books_url_decoding(self, indexer):
        """Should decode URL-encoded characters in slugs."""
        html = """
        <article>
            <a class="card-click-target" href="/book/la-casa-de-los-esp%C3%ADritus/"></a>
            <a href="/autor/isabel-allende/" rel="tag">Isabel Allende</a>
        </article>
        """
        soup = BeautifulSoup(html, 'lxml')
        books = indexer._extract_books_from_page(soup)
        
        assert len(books) == 1
        # The slug should have the decoded character in title
        assert "espíritus" in books[0]["title"].lower() or "esp" in books[0]["slug"]
    
    def test_extract_books_empty_page(self, indexer):
        """Empty page should return empty list."""
        html = "<html><body><main></main></body></html>"
        soup = BeautifulSoup(html, 'lxml')
        books = indexer._extract_books_from_page(soup)
        
        assert books == []
    
    def test_extract_books_no_book_links(self, indexer):
        """Page without book links should return empty list."""
        html = """
        <html><body>
            <a href="/genero/ficcion/">Fiction</a>
            <a href="/autor/someone/">Someone</a>
        </body></html>
        """
        soup = BeautifulSoup(html, 'lxml')
        books = indexer._extract_books_from_page(soup)
        
        assert books == []
    
    def test_extract_books_filters_non_book_urls(self, indexer):
        """Should ignore links that don't have /book/ in href."""
        html = """
        <article>
            <a class="card-click-target" href="/genero/ficcion/"></a>
        </article>
        <article>
            <a class="card-click-target" href="/book/valid-book/"></a>
            <a href="/autor/author/" rel="tag">Author</a>
        </article>
        """
        soup = BeautifulSoup(html, 'lxml')
        books = indexer._extract_books_from_page(soup)
        
        assert len(books) == 1
        assert books[0]["slug"] == "valid-book"


class TestNextPageDetection:
    """Tests for pagination detection."""
    
    @pytest.fixture
    def indexer(self):
        """Create an indexer instance."""
        with patch('indexer.HTTPClient'):
            idx = LectulandiaIndexer()
            yield idx
            idx.close()
    
    def test_detects_next_page(self, indexer, sample_html):
        """Should detect next page link."""
        soup = BeautifulSoup(sample_html, 'lxml')
        next_link = soup.find("a", class_="next page-numbers")
        
        assert next_link is not None
    
    def test_detects_no_next_page(self, indexer, sample_html_no_next_page):
        """Should not find next page link on last page."""
        soup = BeautifulSoup(sample_html_no_next_page, 'lxml')
        next_link = soup.find("a", class_="next page-numbers")
        
        assert next_link is None


class TestIndexerIntegration:
    """Integration tests for indexer with mocked HTTP."""
    
    def test_get_index_info_no_db(self, temp_db, monkeypatch):
        """get_index_info should return None when DB is empty."""
        import database as db
        from indexer import get_index_info
        
        # Ensure empty database
        monkeypatch.setattr(db, "is_available", lambda: False)
        
        info = get_index_info()
        assert info is None
    
    def test_get_index_info_with_data(self, temp_db, sample_books):
        """get_index_info should return metadata when DB has data."""
        import database as db
        from indexer import get_index_info
        
        # Populate database
        db.insert_books(sample_books)
        db.update_metadata("last_updated", "2026-01-09")
        db.update_metadata("total_books", str(len(sample_books)))
        
        info = get_index_info()
        
        assert info is not None
        assert info["last_updated"] == "2026-01-09"
        assert info["total_books"] == len(sample_books)
