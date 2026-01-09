"""
Operations module for checkpoint/resume functionality.

Provides classes to track long-running operations (batch downloads, indexing)
and resume them if they fail or are interrupted.
"""

import hashlib
from datetime import datetime
from typing import Optional

from loguru import logger

import database as db


class DownloadOperation:
    """
    Manages a resumable batch download operation.

    Tracks individual URLs to download and their status,
    allowing resume from where a failed operation left off.
    """

    def __init__(self, operation_id: int):
        """
        Initialize with an existing operation ID.

        Args:
            operation_id: ID from the operations table
        """
        self.operation_id = operation_id
        self._load()

    def _load(self):
        """Load operation data from database."""
        op = db.get_operation(self.operation_id)
        if not op:
            raise ValueError(f"Operation {self.operation_id} not found")
        self.operation_type = op['operation_type']
        self.status = op['status']
        self.context = op.get('context') or {}
        self.checkpoint_data = op.get('checkpoint_data') or {}

    @classmethod
    def create(
        cls,
        download_urls: list[str],
        context: dict = None
    ) -> 'DownloadOperation':
        """
        Create a new download operation with all URLs as pending items.

        Args:
            download_urls: List of URLs to download
            context: Optional context (author, genre, etc.)

        Returns:
            New DownloadOperation instance
        """
        db.init_db()

        # Create operation record
        operation_id = db.create_operation(
            operation_type='batch_download',
            total_items=len(download_urls),
            context=context,
            checkpoint_data={'urls_hash': cls._compute_urls_hash(download_urls)}
        )

        # Add all URLs as operation items
        items = [('book_url', url) for url in download_urls]
        db.add_operation_items(operation_id, items)

        logger.info(f"Created download operation {operation_id} with {len(download_urls)} items")

        return cls(operation_id)

    @classmethod
    def get_resumable(cls, context_filter: dict = None) -> list['DownloadOperation']:
        """
        Find all operations that can be resumed.

        Args:
            context_filter: Optional filter by context values

        Returns:
            List of resumable DownloadOperation instances
        """
        operations = db.get_resumable_operations('batch_download')

        if context_filter:
            operations = [
                op for op in operations
                if all(
                    op.get('context', {}).get(k) == v
                    for k, v in context_filter.items()
                )
            ]

        return [cls(op['id']) for op in operations]

    @classmethod
    def resume_or_create(
        cls,
        download_urls: list[str],
        context: dict = None
    ) -> 'DownloadOperation':
        """
        Resume an existing operation if one matches, otherwise create new.

        Matches by URL hash to find the same batch.

        Args:
            download_urls: List of URLs to download
            context: Optional context

        Returns:
            Existing or new DownloadOperation
        """
        urls_hash = cls._compute_urls_hash(download_urls)

        # Look for existing operation with same URLs
        resumable = db.get_resumable_operations('batch_download')
        for op in resumable:
            checkpoint = op.get('checkpoint_data') or {}
            if checkpoint.get('urls_hash') == urls_hash:
                logger.info(f"Resuming existing operation {op['id']}")
                return cls(op['id'])

        # No match found, create new
        return cls.create(download_urls, context)

    @staticmethod
    def _compute_urls_hash(urls: list[str]) -> str:
        """Compute a hash of the URL list for matching."""
        sorted_urls = '|'.join(sorted(urls))
        return hashlib.md5(sorted_urls.encode()).hexdigest()

    def get_pending_items(self) -> list[str]:
        """
        Get list of URLs still pending download.

        Returns:
            List of URL strings
        """
        items = db.get_pending_operation_items(self.operation_id)
        return [item['item_value'] for item in items]

    def mark_item_completed(self, url: str, result: dict = None) -> None:
        """
        Mark a download URL as successfully completed.

        Args:
            url: The URL that completed
            result: Optional result data (filename, size, etc.)
        """
        db.update_operation_item(
            self.operation_id,
            url,
            'completed',
            result_data=result
        )
        self._update_progress()

    def mark_item_failed(self, url: str, error: str) -> None:
        """
        Mark a download URL as failed.

        Args:
            url: The URL that failed
            error: Error message
        """
        db.update_operation_item(
            self.operation_id,
            url,
            'failed',
            error_message=error
        )
        self._update_progress()

    def mark_item_skipped(self, url: str, reason: str = 'duplicate') -> None:
        """
        Mark a download URL as skipped.

        Args:
            url: The URL that was skipped
            reason: Reason for skipping
        """
        db.update_operation_item(
            self.operation_id,
            url,
            'skipped',
            error_message=reason
        )
        self._update_progress()

    def _update_progress(self) -> None:
        """Update the operation's progress counters."""
        progress = db.get_operation_progress(self.operation_id)
        db.update_operation(
            self.operation_id,
            processed_items=progress['completed'] + progress['failed'] + progress['skipped'],
            successful_items=progress['completed'],
            failed_items=progress['failed'],
            skipped_items=progress['skipped']
        )

    def get_progress(self) -> dict:
        """
        Get current progress.

        Returns:
            dict with: total, pending, completed, failed, skipped
        """
        return db.get_operation_progress(self.operation_id)

    def complete(self) -> None:
        """Mark the entire operation as completed."""
        db.complete_operation(self.operation_id)
        logger.info(f"Operation {self.operation_id} completed")

    def fail(self, error_message: str = None) -> None:
        """Mark the operation as failed."""
        db.fail_operation(self.operation_id, error_message)
        logger.error(f"Operation {self.operation_id} failed: {error_message}")


class IndexOperation:
    """
    Manages a resumable index build/update operation.

    Tracks which page was last processed and buffered books,
    allowing resume from the last checkpoint.
    """

    def __init__(self, operation_id: int):
        """
        Initialize with an existing operation ID.

        Args:
            operation_id: ID from the operations table
        """
        self.operation_id = operation_id
        self._load()

    def _load(self):
        """Load operation data from database."""
        op = db.get_operation(self.operation_id)
        if not op:
            raise ValueError(f"Operation {self.operation_id} not found")
        self.operation_type = op['operation_type']
        self.status = op['status']
        self.context = op.get('context') or {}
        self.checkpoint_data = op.get('checkpoint_data') or {}

    @classmethod
    def create_build(cls, max_pages: int = None) -> 'IndexOperation':
        """
        Create a new index build operation.

        Args:
            max_pages: Maximum pages to scrape (None = unlimited)

        Returns:
            New IndexOperation instance
        """
        db.init_db()

        checkpoint_data = {
            'type': 'build',
            'max_pages': max_pages,
            'current_page': 1,
            'books_buffer': [],
            'total_books_scraped': 0
        }

        operation_id = db.create_operation(
            operation_type='index_build',
            total_items=max_pages or 0,  # 0 = unknown
            context={'max_pages': max_pages},
            checkpoint_data=checkpoint_data
        )

        logger.info(f"Created index build operation {operation_id}")

        return cls(operation_id)

    @classmethod
    def create_update(cls, max_pages: int = 10) -> 'IndexOperation':
        """
        Create a new index update operation.

        Args:
            max_pages: Maximum pages to check for updates

        Returns:
            New IndexOperation instance
        """
        db.init_db()

        checkpoint_data = {
            'type': 'update',
            'max_pages': max_pages,
            'current_page': 1,
            'new_books_found': 0
        }

        operation_id = db.create_operation(
            operation_type='index_update',
            total_items=max_pages,
            context={'max_pages': max_pages},
            checkpoint_data=checkpoint_data
        )

        logger.info(f"Created index update operation {operation_id}")

        return cls(operation_id)

    @classmethod
    def get_resumable_build(cls) -> Optional['IndexOperation']:
        """
        Find an incomplete build operation to resume.

        Returns:
            IndexOperation if found, None otherwise
        """
        operations = db.get_resumable_operations('index_build')
        if operations:
            return cls(operations[0]['id'])
        return None

    @classmethod
    def get_resumable_update(cls) -> Optional['IndexOperation']:
        """
        Find an incomplete update operation to resume.

        Returns:
            IndexOperation if found, None otherwise
        """
        operations = db.get_resumable_operations('index_update')
        if operations:
            return cls(operations[0]['id'])
        return None

    def save_checkpoint(
        self,
        page: int,
        books_buffer: list = None,
        total_books_scraped: int = None
    ) -> None:
        """
        Save current progress for resume.

        Args:
            page: Current page number
            books_buffer: Books waiting to be flushed to DB
            total_books_scraped: Total books scraped so far
        """
        checkpoint = self.checkpoint_data.copy()
        checkpoint['current_page'] = page
        checkpoint['last_checkpoint'] = datetime.now().isoformat()

        if books_buffer is not None:
            checkpoint['books_buffer'] = books_buffer
        if total_books_scraped is not None:
            checkpoint['total_books_scraped'] = total_books_scraped

        db.update_operation(
            self.operation_id,
            processed_items=page,
            checkpoint_data=checkpoint
        )

        self.checkpoint_data = checkpoint
        logger.debug(f"Checkpoint saved at page {page}")

    def get_checkpoint(self) -> dict:
        """
        Get checkpoint data to resume from.

        Returns:
            dict with: current_page, books_buffer, total_books_scraped, etc.
        """
        # Reload to get latest
        self._load()
        return self.checkpoint_data

    def mark_page_completed(self, page: int, books_count: int) -> None:
        """
        Mark a page as successfully scraped.

        Args:
            page: Page number completed
            books_count: Number of books found on this page
        """
        db.update_operation(
            self.operation_id,
            processed_items=page,
            successful_items=(self.checkpoint_data.get('total_books_scraped', 0) + books_count)
        )

    def complete(self, total_books: int = None) -> None:
        """
        Mark the operation as completed.

        Args:
            total_books: Final count of books in index
        """
        checkpoint = self.checkpoint_data.copy()
        if total_books is not None:
            checkpoint['final_total_books'] = total_books

        db.update_operation(
            self.operation_id,
            checkpoint_data=checkpoint,
            status='completed'
        )
        logger.info(f"Index operation {self.operation_id} completed")

    def fail(self, error_message: str = None) -> None:
        """Mark the operation as failed."""
        db.fail_operation(self.operation_id, error_message)
        logger.error(f"Index operation {self.operation_id} failed: {error_message}")


# Convenience functions for CLI usage

def get_all_resumable_operations() -> list[dict]:
    """
    Get all resumable operations with summary info.

    Returns:
        List of operation summaries
    """
    operations = db.get_resumable_operations()
    summaries = []

    for op in operations:
        progress = db.get_operation_progress(op['id'])
        context = op.get('context') or {}

        summary = {
            'id': op['id'],
            'type': op['operation_type'],
            'status': op['status'],
            'started_at': op['started_at'],
            'updated_at': op['updated_at'],
            'progress': progress,
            'context': context
        }

        # Add human-readable description
        if op['operation_type'] == 'batch_download':
            author = context.get('author', '')
            genre = context.get('folder_name', '')
            if author:
                summary['description'] = f"Descarga por autor: {author}"
            elif genre:
                summary['description'] = f"Descarga por género: {genre}"
            else:
                summary['description'] = "Descarga batch"
        elif op['operation_type'] == 'index_build':
            summary['description'] = "Reconstrucción de índice"
        elif op['operation_type'] == 'index_update':
            summary['description'] = "Actualización de índice"
        else:
            summary['description'] = op['operation_type']

        summaries.append(summary)

    return summaries


def cancel_operation(operation_id: int) -> None:
    """
    Cancel a running operation.

    Args:
        operation_id: Operation to cancel
    """
    db.update_operation(operation_id, status='cancelled')
    logger.info(f"Operation {operation_id} cancelled")


def cleanup_stale_operations(max_age_hours: int = 24) -> int:
    """
    Mark operations as failed if they've been running too long without updates.

    Args:
        max_age_hours: Hours after which a running operation is considered stale

    Returns:
        Number of operations marked as failed
    """
    from datetime import timedelta

    cutoff = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()

    operations = db.get_resumable_operations()
    cleaned = 0

    for op in operations:
        if op['status'] == 'running' and op['updated_at'] < cutoff:
            db.fail_operation(op['id'], f'Stale operation (no update in {max_age_hours}h)')
            cleaned += 1
            logger.warning(f"Marked stale operation {op['id']} as failed")

    return cleaned
