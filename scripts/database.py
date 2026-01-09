"""
Database module for SQLite storage with FTS5 full-text search.

This module provides fast search capabilities using SQLite's FTS5
extension, replacing the slower JSON + rapidfuzz approach.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

from loguru import logger

# Database file path
DATA_DIR = Path(__file__).parent.parent / "data"
DB_FILE = DATA_DIR / "catalog.db"
JSON_FILE = DATA_DIR / "catalog_index.json"


@contextmanager
def get_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Initialize the database with tables and FTS5 virtual table."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        cursor = conn.cursor()

        # Main books table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                author TEXT,
                slug TEXT UNIQUE NOT NULL,
                url TEXT NOT NULL
            )
        ''')

        # Check if FTS table exists
        cursor.execute('''
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='books_fts'
        ''')

        if not cursor.fetchone():
            # FTS5 virtual table for fast search
            cursor.execute('''
                CREATE VIRTUAL TABLE books_fts USING fts5(
                    title, author, slug,
                    content='books',
                    content_rowid='id'
                )
            ''')

            # Triggers to keep FTS in sync
            cursor.execute('''
                CREATE TRIGGER IF NOT EXISTS books_ai AFTER INSERT ON books BEGIN
                    INSERT INTO books_fts(rowid, title, author, slug)
                    VALUES (new.id, new.title, new.author, new.slug);
                END
            ''')

            cursor.execute('''
                CREATE TRIGGER IF NOT EXISTS books_ad AFTER DELETE ON books BEGIN
                    INSERT INTO books_fts(books_fts, rowid, title, author, slug)
                    VALUES ('delete', old.id, old.title, old.author, old.slug);
                END
            ''')

            cursor.execute('''
                CREATE TRIGGER IF NOT EXISTS books_au AFTER UPDATE ON books BEGIN
                    INSERT INTO books_fts(books_fts, rowid, title, author, slug)
                    VALUES ('delete', old.id, old.title, old.author, old.slug);
                    INSERT INTO books_fts(rowid, title, author, slug)
                    VALUES (new.id, new.title, new.author, new.slug);
                END
            ''')

        # Metadata table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        # Index on slug for fast lookups
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_books_slug ON books(slug)
        ''')

        conn.commit()
        logger.info(f"Database initialized at {DB_FILE}")


def insert_books(books: list[dict], clear_existing: bool = False) -> int:
    """
    Insert books into the database.

    Args:
        books: List of book dictionaries with title, author, slug, url
        clear_existing: If True, delete all existing books first

    Returns:
        Number of books inserted
    """
    init_db()

    with get_connection() as conn:
        cursor = conn.cursor()

        if clear_existing:
            cursor.execute('DELETE FROM books')
            # Rebuild FTS index
            cursor.execute("INSERT INTO books_fts(books_fts) VALUES('rebuild')")

        inserted = 0
        for book in books:
            try:
                cursor.execute('''
                    INSERT OR IGNORE INTO books (title, author, slug, url)
                    VALUES (?, ?, ?, ?)
                ''', (
                    book.get('title', ''),
                    book.get('author', 'Desconocido'),
                    book['slug'],
                    book['url']
                ))
                if cursor.rowcount > 0:
                    inserted += 1
            except sqlite3.Error as e:
                logger.debug(f"Error inserting book {book.get('slug')}: {e}")
                continue

        conn.commit()
        return inserted


def update_metadata(key: str, value: str) -> None:
    """Update or insert a metadata value."""
    with get_connection() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)
        ''', (key, value))
        conn.commit()


def get_metadata() -> dict:
    """Get all metadata as a dictionary."""
    if not DB_FILE.exists():
        return {}

    with get_connection() as conn:
        cursor = conn.execute('SELECT key, value FROM metadata')
        return {row['key']: row['value'] for row in cursor.fetchall()}


def get_total_books() -> int:
    """Get total number of books in the database."""
    if not DB_FILE.exists():
        return 0

    with get_connection() as conn:
        cursor = conn.execute('SELECT COUNT(*) FROM books')
        return cursor.fetchone()[0]


def search_books(
    query: str,
    search_by: str = "all",
    limit: int = 20
) -> list[dict]:
    """
    Search books using FTS5.

    Args:
        query: Search query string
        search_by: "title", "author", or "all"
        limit: Maximum number of results

    Returns:
        List of matching books
    """
    if not DB_FILE.exists():
        return []

    # Escape special FTS5 characters and prepare query
    # FTS5 uses * for prefix matching
    safe_query = query.replace('"', '""')

    # Add prefix matching for partial words
    terms = safe_query.split()
    fts_query = ' '.join(f'"{term}"*' for term in terms if term)

    if not fts_query:
        return []

    with get_connection() as conn:
        cursor = conn.cursor()

        if search_by == "title":
            sql = '''
                SELECT b.*, bm.rank
                FROM books b
                JOIN (
                    SELECT rowid, rank FROM books_fts
                    WHERE title MATCH ?
                    ORDER BY rank
                    LIMIT ?
                ) bm ON b.id = bm.rowid
            '''
        elif search_by == "author":
            sql = '''
                SELECT b.*, bm.rank
                FROM books b
                JOIN (
                    SELECT rowid, rank FROM books_fts
                    WHERE author MATCH ?
                    ORDER BY rank
                    LIMIT ?
                ) bm ON b.id = bm.rowid
            '''
        else:  # "all"
            sql = '''
                SELECT b.*, bm.rank
                FROM books b
                JOIN (
                    SELECT rowid, rank FROM books_fts
                    WHERE books_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                ) bm ON b.id = bm.rowid
            '''

        try:
            cursor.execute(sql, (fts_query, limit))
            results = []
            for row in cursor.fetchall():
                book = dict(row)
                # Convert FTS rank to a percentage-like score (higher is better)
                # FTS5 BM25 rank is negative, more negative = better match
                # Typical range: -25 (excellent) to -5 (poor)
                rank = book.pop('rank', 0)
                # Transform: -25 → 100%, -15 → 80%, -10 → 70%, -5 → 60%
                score = min(100, max(50, int(50 + abs(rank) * 2)))
                book['score'] = score
                results.append(book)
            return results
        except sqlite3.OperationalError as e:
            logger.warning(f"FTS query error: {e}")
            return []


def get_book_by_slug(slug: str) -> Optional[dict]:
    """Get a single book by its slug."""
    if not DB_FILE.exists():
        return None

    with get_connection() as conn:
        cursor = conn.execute(
            'SELECT * FROM books WHERE slug = ?', (slug,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def slug_exists(slug: str) -> bool:
    """Check if a slug already exists in the database."""
    if not DB_FILE.exists():
        return False

    with get_connection() as conn:
        cursor = conn.execute(
            'SELECT 1 FROM books WHERE slug = ? LIMIT 1', (slug,)
        )
        return cursor.fetchone() is not None


def get_existing_slugs() -> set:
    """Get all existing slugs as a set for fast lookup."""
    if not DB_FILE.exists():
        return set()

    with get_connection() as conn:
        cursor = conn.execute('SELECT slug FROM books')
        return {row['slug'] for row in cursor.fetchall()}


def migrate_from_json() -> int:
    """
    Migrate existing JSON index to SQLite.

    Returns:
        Number of books migrated
    """
    if not JSON_FILE.exists():
        logger.warning(f"JSON file not found: {JSON_FILE}")
        return 0

    logger.info(f"Loading JSON from {JSON_FILE}...")

    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    books = data.get("books", [])
    metadata = data.get("metadata", {})

    if not books:
        logger.warning("No books found in JSON file")
        return 0

    logger.info(f"Migrating {len(books)} books to SQLite...")

    # Initialize and clear database
    init_db()

    # Insert all books
    inserted = insert_books(books, clear_existing=True)

    # Migrate metadata
    for key, value in metadata.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        update_metadata(key, str(value))

    update_metadata("migrated_from_json", datetime.now().isoformat())

    logger.info(f"Migration complete: {inserted} books inserted")
    return inserted


def is_available() -> bool:
    """Check if the database exists and has books."""
    return DB_FILE.exists() and get_total_books() > 0


def get_random_books(count: int = 10) -> list[dict]:
    """Get random books from the database."""
    if not DB_FILE.exists():
        return []

    with get_connection() as conn:
        cursor = conn.execute('''
            SELECT * FROM books ORDER BY RANDOM() LIMIT ?
        ''', (count,))
        return [dict(row) for row in cursor.fetchall()]


if __name__ == "__main__":
    # Quick test / migration
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--migrate":
        count = migrate_from_json()
        print(f"Migrated {count} books")
    else:
        print(f"Database: {DB_FILE}")
        print(f"Available: {is_available()}")
        print(f"Total books: {get_total_books()}")
