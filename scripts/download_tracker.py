"""
Download tracker module for managing book download state.

Provides efficient duplicate detection and download history tracking
using the SQLite database instead of filesystem-only checks.
"""

import os
import re
from pathlib import Path
from typing import Optional
from datetime import datetime
from unidecode import unidecode

from loguru import logger

import database as db


class DownloadTracker:
    """
    Tracks downloaded books for duplicate prevention and status queries.

    Features:
    - Fast duplicate detection via database lookup
    - Links catalog books to local filesystem
    - Supports querying download status
    - Can sync with existing filesystem downloads
    """

    def __init__(self):
        """Initialize the tracker and ensure database tables exist."""
        db.init_db()

    def is_downloaded(self, slug: str) -> bool:
        """
        Check if a book is already downloaded.

        Args:
            slug: Book slug to check

        Returns:
            True if already downloaded successfully
        """
        return db.is_slug_downloaded(slug)

    def get_download_status(self, slug: str) -> Optional[dict]:
        """
        Get full download status for a book.

        Returns:
            Download record dict or None if not found
        """
        return db.get_download_by_slug(slug)

    def record_download(
        self,
        slug: str,
        title: str,
        author: str,
        source_url: str,
        file_path: str,
        file_size: int,
        download_mode: str = 'catalog'
    ) -> int:
        """
        Record a successful download.

        Args:
            slug: Book slug (unique identifier)
            title: Book title
            author: Author name
            source_url: URL the book was downloaded from
            file_path: Local file path (relative to download folder)
            file_size: File size in bytes
            download_mode: 'author', 'genre', 'catalog', or 'direct'

        Returns:
            ID of the downloads record
        """
        return db.insert_download(
            slug=slug,
            title=title,
            author=author,
            source_url=source_url,
            file_path=file_path,
            file_size=file_size,
            status='completed',
            download_mode=download_mode
        )

    def record_skip(self, slug: str, source_url: str, reason: str = 'duplicate') -> None:
        """
        Record a skipped download (duplicate, etc.).

        Args:
            slug: Book slug
            source_url: URL that was skipped
            reason: Reason for skipping
        """
        db.insert_download(
            slug=slug,
            title='',
            author='',
            source_url=source_url,
            status='skipped',
            error_message=reason
        )

    def record_failure(self, slug: str, source_url: str, error: str) -> None:
        """
        Record a failed download attempt.

        Args:
            slug: Book slug
            source_url: URL that failed
            error: Error message
        """
        db.insert_download(
            slug=slug,
            title='',
            author='',
            source_url=source_url,
            status='failed',
            error_message=error
        )

    def get_downloaded_slugs(self) -> set:
        """
        Get set of all successfully downloaded slugs.

        Returns:
            Set of slug strings
        """
        return db.get_downloaded_slugs()

    def get_stats(self) -> dict:
        """
        Get download statistics.

        Returns:
            dict with keys: total_catalog, downloaded, failed, pending, percentage
        """
        return db.get_download_stats()

    def sync_with_filesystem(
        self,
        download_folder: str,
        progress_callback=None
    ) -> dict:
        """
        Scan filesystem and populate download records.

        Useful for:
        - Initial migration from filesystem-only detection
        - Recovery after database loss
        - Syncing after manual file operations

        Args:
            download_folder: Base download folder to scan
            progress_callback: Optional callback(current, total) for progress

        Returns:
            dict with: found, added, already_tracked counts
        """
        download_path = Path(download_folder)

        if not download_path.exists():
            logger.warning(f"Download folder does not exist: {download_folder}")
            return {'found': 0, 'added': 0, 'already_tracked': 0}

        found_books = []

        # Scan for EPUB files in Author/Book/ or Genre/Author/Book/ structure
        for epub_file in download_path.rglob("*.epub"):
            try:
                # Determine structure from path depth
                relative = epub_file.relative_to(download_path)
                parts = relative.parts

                if len(parts) >= 2:
                    # At minimum: Author/book.epub or Author/Book/book.epub
                    book_name = epub_file.stem
                    author = parts[0]  # First folder is author or genre

                    # Try to extract slug from book name
                    slug = self._name_to_slug(book_name)

                    found_books.append({
                        'slug': slug,
                        'title': book_name,
                        'author': author,
                        'file_path': str(relative),
                        'file_size': epub_file.stat().st_size
                    })
            except Exception as e:
                logger.debug(f"Error processing {epub_file}: {e}")
                continue

        logger.info(f"Found {len(found_books)} EPUB files in {download_folder}")

        # Record in database
        added = 0
        already_tracked = 0
        total = len(found_books)

        for i, book in enumerate(found_books):
            if progress_callback:
                progress_callback(i + 1, total)

            if not self.is_downloaded(book['slug']):
                db.insert_download(
                    slug=book['slug'],
                    title=book['title'],
                    author=book['author'],
                    source_url='filesystem_sync',
                    file_path=book['file_path'],
                    file_size=book['file_size'],
                    status='completed',
                    download_mode='migrated'
                )
                added += 1
            else:
                already_tracked += 1

        logger.info(f"Sync complete: {added} added, {already_tracked} already tracked")

        return {
            'found': len(found_books),
            'added': added,
            'already_tracked': already_tracked
        }

    @staticmethod
    def _name_to_slug(name: str) -> str:
        """
        Convert a book name to a slug format.

        Args:
            name: Book name (e.g., "Cien Años de Soledad")

        Returns:
            Slug (e.g., "cien-anos-de-soledad")
        """
        # Normalize unicode characters
        normalized = unidecode(name)
        # Convert to lowercase
        lower = normalized.lower()
        # Replace spaces and special chars with hyphens
        slug = re.sub(r'[^a-z0-9]+', '-', lower)
        # Remove leading/trailing hyphens
        slug = slug.strip('-')
        return slug

    @staticmethod
    def extract_slug_from_url(url: str) -> Optional[str]:
        """
        Extract book slug from a Lectulandia URL.

        Args:
            url: Full URL or download URL

        Returns:
            Extracted slug or None
        """
        # Pattern for book URLs: /book/slug/ or download.php?...&slug=...
        patterns = [
            r'/book/([^/]+)/?',
            r'download\.php\?.*slug=([^&]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None


# Convenience function for CLI usage
def get_tracker() -> DownloadTracker:
    """Get a configured DownloadTracker instance."""
    return DownloadTracker()
