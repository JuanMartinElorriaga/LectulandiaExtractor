"""
Database module for SQLite storage with FTS5 full-text search.

This module provides fast search capabilities using SQLite's FTS5
extension, replacing the slower JSON + rapidfuzz approach.

Includes schema versioning and migration system for evolving the database.
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

# Schema version - increment when adding migrations
SCHEMA_VERSION = 2


@contextmanager
def get_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _get_schema_version() -> int:
    """Get current database schema version."""
    if not DB_FILE.exists():
        return 0

    try:
        with get_connection() as conn:
            cursor = conn.execute(
                "SELECT value FROM metadata WHERE key = 'schema_version'"
            )
            row = cursor.fetchone()
            return int(row['value']) if row else 1
    except sqlite3.OperationalError:
        return 0  # Table doesn't exist


def _set_schema_version(version: int) -> None:
    """Set the schema version in metadata."""
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ('schema_version', str(version))
        )
        conn.commit()


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """
    Migration v1 -> v2: Add downloads, operations, and operation_items tables.

    These tables enable:
    - Download tracking (which books have been downloaded)
    - Operation checkpointing (resume failed batch operations)
    """
    logger.info("Applying migration v1 -> v2: Adding download tracking tables")

    # Downloads table - tracks downloaded books
    conn.execute('''
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY,
            book_id INTEGER,
            slug TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            author TEXT,
            source_url TEXT NOT NULL,
            file_path TEXT,
            file_size INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',
            error_message TEXT,
            download_mode TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE SET NULL
        )
    ''')

    # Operations table - tracks long-running operations for resume
    conn.execute('''
        CREATE TABLE IF NOT EXISTS operations (
            id INTEGER PRIMARY KEY,
            operation_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            total_items INTEGER,
            processed_items INTEGER DEFAULT 0,
            successful_items INTEGER DEFAULT 0,
            failed_items INTEGER DEFAULT 0,
            skipped_items INTEGER DEFAULT 0,
            checkpoint_data TEXT,
            context TEXT,
            error_message TEXT,
            started_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT
        )
    ''')

    # Operation items table - individual items within an operation
    conn.execute('''
        CREATE TABLE IF NOT EXISTS operation_items (
            id INTEGER PRIMARY KEY,
            operation_id INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            item_value TEXT NOT NULL,
            item_order INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            result_data TEXT,
            error_message TEXT,
            processed_at TEXT,
            FOREIGN KEY (operation_id) REFERENCES operations(id) ON DELETE CASCADE
        )
    ''')

    # Create indexes
    conn.execute('CREATE INDEX IF NOT EXISTS idx_downloads_status ON downloads(status)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_downloads_slug ON downloads(slug)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_operations_status ON operations(status)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_operations_type_status ON operations(operation_type, status)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_op_items_operation_status ON operation_items(operation_id, status)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_op_items_order ON operation_items(operation_id, item_order)')

    conn.commit()
    logger.info("Migration v1 -> v2 complete")


def _run_migrations() -> None:
    """Run any pending database migrations."""
    current_version = _get_schema_version()

    if current_version >= SCHEMA_VERSION:
        return  # Already up to date

    migrations = {
        2: _migrate_v1_to_v2,
    }

    with get_connection() as conn:
        for version in range(current_version + 1, SCHEMA_VERSION + 1):
            if version in migrations:
                logger.info(f"Running migration to version {version}")
                migrations[version](conn)

        # Update schema version
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ('schema_version', str(SCHEMA_VERSION))
        )
        conn.commit()

    logger.info(f"Database schema updated to version {SCHEMA_VERSION}")


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

    # Run any pending migrations
    _run_migrations()


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


# =============================================================================
# Download Tracking Functions
# =============================================================================

def get_download_by_slug(slug: str) -> Optional[dict]:
    """Get download record by slug."""
    if not DB_FILE.exists():
        return None

    with get_connection() as conn:
        cursor = conn.execute(
            'SELECT * FROM downloads WHERE slug = ?', (slug,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def is_slug_downloaded(slug: str) -> bool:
    """Check if a book slug has been successfully downloaded."""
    if not DB_FILE.exists():
        return False

    try:
        with get_connection() as conn:
            cursor = conn.execute(
                "SELECT status FROM downloads WHERE slug = ? AND status = 'completed'",
                (slug,)
            )
            return cursor.fetchone() is not None
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        return False


def insert_download(
    slug: str,
    title: str,
    author: str,
    source_url: str,
    file_path: str = None,
    file_size: int = None,
    status: str = 'completed',
    download_mode: str = None,
    error_message: str = None
) -> int:
    """
    Insert or update a download record.

    Returns:
        ID of the inserted/updated record
    """
    init_db()  # Ensure tables exist

    now = datetime.now().isoformat()

    # Try to link to catalog book
    book_id = None
    book = get_book_by_slug(slug)
    if book:
        book_id = book.get('id')

    with get_connection() as conn:
        cursor = conn.execute('''
            INSERT INTO downloads (
                book_id, slug, title, author, source_url,
                file_path, file_size, status, error_message,
                download_mode, created_at, updated_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                title = excluded.title,
                author = excluded.author,
                source_url = excluded.source_url,
                file_path = excluded.file_path,
                file_size = excluded.file_size,
                status = excluded.status,
                error_message = excluded.error_message,
                download_mode = excluded.download_mode,
                updated_at = excluded.updated_at,
                completed_at = excluded.completed_at
        ''', (
            book_id, slug, title, author, source_url,
            file_path, file_size, status, error_message,
            download_mode, now, now,
            now if status == 'completed' else None
        ))
        conn.commit()
        return cursor.lastrowid


def get_downloaded_slugs() -> set:
    """Get set of all successfully downloaded slugs."""
    if not DB_FILE.exists():
        return set()

    try:
        with get_connection() as conn:
            cursor = conn.execute(
                "SELECT slug FROM downloads WHERE status = 'completed'"
            )
            return {row['slug'] for row in cursor.fetchall()}
    except sqlite3.OperationalError:
        return set()


def get_download_stats() -> dict:
    """Get download statistics."""
    if not DB_FILE.exists():
        return {'total_catalog': 0, 'total_attempted': 0, 'downloaded': 0, 'failed': 0, 'skipped': 0, 'pending': 0, 'percentage': 0}

    try:
        with get_connection() as conn:
            # Total catalog books (for reference only)
            cursor = conn.execute("SELECT COUNT(*) FROM books")
            total_catalog = cursor.fetchone()[0]

            # Downloaded (completed)
            cursor = conn.execute(
                "SELECT COUNT(*) FROM downloads WHERE status = 'completed'"
            )
            downloaded = cursor.fetchone()[0]

            # Failed
            cursor = conn.execute(
                "SELECT COUNT(*) FROM downloads WHERE status = 'failed'"
            )
            failed = cursor.fetchone()[0]

            # Skipped (duplicates)
            cursor = conn.execute(
                "SELECT COUNT(*) FROM downloads WHERE status = 'skipped'"
            )
            skipped = cursor.fetchone()[0]

            # Pending (in downloads table, not yet processed)
            cursor = conn.execute(
                "SELECT COUNT(*) FROM downloads WHERE status = 'pending'"
            )
            pending = cursor.fetchone()[0]

            # Total attempted = all entries in downloads table
            total_attempted = downloaded + failed + skipped + pending

            # Percentage based on attempted downloads (success rate)
            # Success = downloaded + skipped (skipped means already had it)
            processed = downloaded + failed + skipped
            if processed > 0:
                percentage = round((downloaded + skipped) / processed * 100, 2)
            else:
                percentage = 0

            return {
                'total_catalog': total_catalog,
                'total_attempted': total_attempted,
                'downloaded': downloaded,
                'failed': failed,
                'skipped': skipped,
                'pending': pending,
                'percentage': percentage
            }
    except sqlite3.OperationalError:
        return {'total_catalog': 0, 'total_attempted': 0, 'downloaded': 0, 'failed': 0, 'skipped': 0, 'pending': 0, 'percentage': 0}


# =============================================================================
# Operations (Checkpoint/Resume) Functions
# =============================================================================

def create_operation(
    operation_type: str,
    total_items: int,
    context: dict = None,
    checkpoint_data: dict = None
) -> int:
    """
    Create a new operation for tracking.

    Args:
        operation_type: 'batch_download', 'index_build', 'index_update'
        total_items: Total number of items to process
        context: JSON-serializable context (author, genre, etc.)
        checkpoint_data: Initial checkpoint data

    Returns:
        Operation ID
    """
    init_db()

    now = datetime.now().isoformat()

    with get_connection() as conn:
        cursor = conn.execute('''
            INSERT INTO operations (
                operation_type, status, total_items,
                context, checkpoint_data,
                started_at, updated_at
            ) VALUES (?, 'running', ?, ?, ?, ?, ?)
        ''', (
            operation_type, total_items,
            json.dumps(context) if context else None,
            json.dumps(checkpoint_data) if checkpoint_data else None,
            now, now
        ))
        conn.commit()
        return cursor.lastrowid


def get_operation(operation_id: int) -> Optional[dict]:
    """Get an operation by ID."""
    if not DB_FILE.exists():
        return None

    with get_connection() as conn:
        cursor = conn.execute(
            'SELECT * FROM operations WHERE id = ?', (operation_id,)
        )
        row = cursor.fetchone()
        if row:
            op = dict(row)
            # Parse JSON fields
            if op.get('context'):
                op['context'] = json.loads(op['context'])
            if op.get('checkpoint_data'):
                op['checkpoint_data'] = json.loads(op['checkpoint_data'])
            return op
        return None


def get_resumable_operations(operation_type: str = None) -> list[dict]:
    """
    Get operations that can be resumed (status = 'running' or 'failed').

    Args:
        operation_type: Optional filter by type

    Returns:
        List of resumable operations
    """
    if not DB_FILE.exists():
        return []

    try:
        with get_connection() as conn:
            if operation_type:
                cursor = conn.execute('''
                    SELECT * FROM operations
                    WHERE status IN ('running', 'failed')
                    AND operation_type = ?
                    ORDER BY updated_at DESC
                ''', (operation_type,))
            else:
                cursor = conn.execute('''
                    SELECT * FROM operations
                    WHERE status IN ('running', 'failed')
                    ORDER BY updated_at DESC
                ''')

            results = []
            for row in cursor.fetchall():
                op = dict(row)
                if op.get('context'):
                    op['context'] = json.loads(op['context'])
                if op.get('checkpoint_data'):
                    op['checkpoint_data'] = json.loads(op['checkpoint_data'])
                results.append(op)
            return results
    except sqlite3.OperationalError:
        return []


def update_operation(
    operation_id: int,
    processed_items: int = None,
    successful_items: int = None,
    failed_items: int = None,
    skipped_items: int = None,
    checkpoint_data: dict = None,
    status: str = None,
    error_message: str = None
) -> None:
    """Update an operation's progress."""
    now = datetime.now().isoformat()

    updates = ['updated_at = ?']
    params = [now]

    if processed_items is not None:
        updates.append('processed_items = ?')
        params.append(processed_items)
    if successful_items is not None:
        updates.append('successful_items = ?')
        params.append(successful_items)
    if failed_items is not None:
        updates.append('failed_items = ?')
        params.append(failed_items)
    if skipped_items is not None:
        updates.append('skipped_items = ?')
        params.append(skipped_items)
    if checkpoint_data is not None:
        updates.append('checkpoint_data = ?')
        params.append(json.dumps(checkpoint_data))
    if status is not None:
        updates.append('status = ?')
        params.append(status)
        if status == 'completed':
            updates.append('completed_at = ?')
            params.append(now)
    if error_message is not None:
        updates.append('error_message = ?')
        params.append(error_message)

    params.append(operation_id)

    with get_connection() as conn:
        conn.execute(
            f"UPDATE operations SET {', '.join(updates)} WHERE id = ?",
            params
        )
        conn.commit()


def complete_operation(operation_id: int) -> None:
    """Mark an operation as completed."""
    update_operation(operation_id, status='completed')


def fail_operation(operation_id: int, error_message: str = None) -> None:
    """Mark an operation as failed."""
    update_operation(operation_id, status='failed', error_message=error_message)


# =============================================================================
# Operation Items Functions
# =============================================================================

def add_operation_items(operation_id: int, items: list[tuple[str, str]]) -> int:
    """
    Add items to an operation.

    Args:
        operation_id: The operation ID
        items: List of (item_type, item_value) tuples

    Returns:
        Number of items added
    """
    with get_connection() as conn:
        cursor = conn.executemany('''
            INSERT INTO operation_items (operation_id, item_type, item_value, item_order, status)
            VALUES (?, ?, ?, ?, 'pending')
        ''', [
            (operation_id, item_type, item_value, i)
            for i, (item_type, item_value) in enumerate(items)
        ])
        conn.commit()
        return cursor.rowcount


def get_pending_operation_items(operation_id: int) -> list[dict]:
    """Get pending items for an operation."""
    with get_connection() as conn:
        cursor = conn.execute('''
            SELECT * FROM operation_items
            WHERE operation_id = ? AND status = 'pending'
            ORDER BY item_order
        ''', (operation_id,))
        return [dict(row) for row in cursor.fetchall()]


def update_operation_item(
    operation_id: int,
    item_value: str,
    status: str,
    result_data: dict = None,
    error_message: str = None
) -> None:
    """Update an operation item's status."""
    now = datetime.now().isoformat()

    with get_connection() as conn:
        conn.execute('''
            UPDATE operation_items
            SET status = ?, result_data = ?, error_message = ?, processed_at = ?
            WHERE operation_id = ? AND item_value = ?
        ''', (
            status,
            json.dumps(result_data) if result_data else None,
            error_message,
            now,
            operation_id,
            item_value
        ))
        conn.commit()


def get_operation_progress(operation_id: int) -> dict:
    """Get detailed progress for an operation."""
    with get_connection() as conn:
        cursor = conn.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) as skipped
            FROM operation_items
            WHERE operation_id = ?
        ''', (operation_id,))
        row = cursor.fetchone()
        return dict(row) if row else {'total': 0, 'pending': 0, 'completed': 0, 'failed': 0, 'skipped': 0}


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
