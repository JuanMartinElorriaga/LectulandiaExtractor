"""
Tests for the operations module (checkpoint/resume functionality).
"""

import pytest


class TestDownloadOperation:
    """Tests for DownloadOperation class."""

    def test_create_operation(self, temp_db):
        """Creating an operation should store items."""
        from operations import DownloadOperation

        urls = [
            "https://example.com/book/book-1/",
            "https://example.com/book/book-2/",
            "https://example.com/book/book-3/",
        ]

        operation = DownloadOperation.create(urls, context={"author": "Test Author"})

        assert operation.operation_id is not None
        assert operation.operation_type == "batch_download"
        assert operation.status == "running"
        assert operation.context == {"author": "Test Author"}

    def test_get_pending_items(self, temp_db):
        """get_pending_items should return all URLs initially."""
        from operations import DownloadOperation

        urls = [
            "https://example.com/book/book-1/",
            "https://example.com/book/book-2/",
        ]

        operation = DownloadOperation.create(urls)
        pending = operation.get_pending_items()

        assert len(pending) == 2
        assert "https://example.com/book/book-1/" in pending
        assert "https://example.com/book/book-2/" in pending

    def test_mark_item_completed(self, temp_db):
        """Marking an item as completed should remove it from pending."""
        from operations import DownloadOperation

        urls = ["https://example.com/book/book-1/", "https://example.com/book/book-2/"]
        operation = DownloadOperation.create(urls)

        operation.mark_item_completed(
            "https://example.com/book/book-1/",
            result={"filename": "book-1.epub", "size": "1MB"}
        )

        pending = operation.get_pending_items()
        assert len(pending) == 1
        assert "https://example.com/book/book-1/" not in pending
        assert "https://example.com/book/book-2/" in pending

    def test_mark_item_failed(self, temp_db):
        """Marking an item as failed should remove it from pending."""
        from operations import DownloadOperation

        urls = ["https://example.com/book/book-1/"]
        operation = DownloadOperation.create(urls)

        operation.mark_item_failed(
            "https://example.com/book/book-1/",
            error="Connection timeout"
        )

        pending = operation.get_pending_items()
        assert len(pending) == 0

    def test_mark_item_skipped(self, temp_db):
        """Marking an item as skipped should remove it from pending."""
        from operations import DownloadOperation

        urls = ["https://example.com/book/book-1/"]
        operation = DownloadOperation.create(urls)

        operation.mark_item_skipped(
            "https://example.com/book/book-1/",
            reason="duplicate"
        )

        pending = operation.get_pending_items()
        assert len(pending) == 0

    def test_get_progress(self, temp_db):
        """get_progress should return accurate counts."""
        from operations import DownloadOperation

        urls = [
            "https://example.com/book/book-1/",
            "https://example.com/book/book-2/",
            "https://example.com/book/book-3/",
            "https://example.com/book/book-4/",
        ]
        operation = DownloadOperation.create(urls)

        operation.mark_item_completed("https://example.com/book/book-1/")
        operation.mark_item_failed("https://example.com/book/book-2/", "Error")
        operation.mark_item_skipped("https://example.com/book/book-3/", "dup")

        progress = operation.get_progress()

        assert progress["total"] == 4
        assert progress["completed"] == 1
        assert progress["failed"] == 1
        assert progress["skipped"] == 1
        assert progress["pending"] == 1

    def test_complete_operation(self, temp_db):
        """complete() should mark operation as completed."""
        from operations import DownloadOperation
        import database as db

        urls = ["https://example.com/book/book-1/"]
        operation = DownloadOperation.create(urls)
        operation.mark_item_completed("https://example.com/book/book-1/")
        operation.complete()

        # Reload from DB
        op_data = db.get_operation(operation.operation_id)
        assert op_data["status"] == "completed"
        assert op_data["completed_at"] is not None

    def test_fail_operation(self, temp_db):
        """fail() should mark operation as failed with error message."""
        from operations import DownloadOperation
        import database as db

        urls = ["https://example.com/book/book-1/"]
        operation = DownloadOperation.create(urls)
        operation.fail("Network error")

        op_data = db.get_operation(operation.operation_id)
        assert op_data["status"] == "failed"
        assert op_data["error_message"] == "Network error"

    def test_get_resumable(self, temp_db):
        """get_resumable should return incomplete operations."""
        from operations import DownloadOperation

        # Create two operations
        op1 = DownloadOperation.create(["url1"])
        op2 = DownloadOperation.create(["url2"])

        # Complete one
        op1.mark_item_completed("url1")
        op1.complete()

        # Leave other running
        resumable = DownloadOperation.get_resumable()

        assert len(resumable) == 1
        assert resumable[0].operation_id == op2.operation_id

    def test_resume_or_create_creates_new(self, temp_db):
        """resume_or_create should create new operation if none matches."""
        from operations import DownloadOperation

        urls = ["url1", "url2"]
        operation = DownloadOperation.resume_or_create(urls, {"test": True})

        assert operation.operation_id is not None
        assert len(operation.get_pending_items()) == 2

    def test_resume_or_create_resumes_existing(self, temp_db):
        """resume_or_create should resume matching operation."""
        from operations import DownloadOperation

        urls = ["url1", "url2", "url3"]

        # Create initial operation
        op1 = DownloadOperation.create(urls)
        op1.mark_item_completed("url1")
        # Don't complete - leave it running

        # Try to resume with same URLs
        op2 = DownloadOperation.resume_or_create(urls)

        assert op2.operation_id == op1.operation_id
        pending = op2.get_pending_items()
        assert len(pending) == 2  # url2 and url3 still pending


class TestIndexOperation:
    """Tests for IndexOperation class."""

    def test_create_build(self, temp_db):
        """create_build should create an index build operation."""
        from operations import IndexOperation

        operation = IndexOperation.create_build(max_pages=100)

        assert operation.operation_id is not None
        assert operation.operation_type == "index_build"
        assert operation.status == "running"

    def test_create_update(self, temp_db):
        """create_update should create an index update operation."""
        from operations import IndexOperation

        operation = IndexOperation.create_update(max_pages=10)

        assert operation.operation_id is not None
        assert operation.operation_type == "index_update"
        assert operation.status == "running"

    def test_save_checkpoint(self, temp_db):
        """save_checkpoint should persist progress."""
        from operations import IndexOperation

        operation = IndexOperation.create_build(max_pages=100)

        operation.save_checkpoint(
            page=25,
            books_buffer=[{"title": "Book 1"}],
            total_books_scraped=500
        )

        # Reload checkpoint
        checkpoint = operation.get_checkpoint()

        assert checkpoint["current_page"] == 25
        assert checkpoint["books_buffer"] == [{"title": "Book 1"}]
        assert checkpoint["total_books_scraped"] == 500

    def test_get_resumable_build(self, temp_db):
        """get_resumable_build should return incomplete build operation."""
        from operations import IndexOperation

        # Create and leave running
        op1 = IndexOperation.create_build(max_pages=100)
        op1.save_checkpoint(page=50, total_books_scraped=1000)

        # Should find it
        resumable = IndexOperation.get_resumable_build()

        assert resumable is not None
        assert resumable.operation_id == op1.operation_id

    def test_get_resumable_build_none_if_completed(self, temp_db):
        """get_resumable_build should return None if all complete."""
        from operations import IndexOperation

        op1 = IndexOperation.create_build(max_pages=100)
        op1.complete(total_books=5000)

        resumable = IndexOperation.get_resumable_build()
        assert resumable is None

    def test_get_resumable_update(self, temp_db):
        """get_resumable_update should return incomplete update operation."""
        from operations import IndexOperation

        op1 = IndexOperation.create_update(max_pages=10)
        op1.save_checkpoint(page=5, total_books_scraped=50)

        resumable = IndexOperation.get_resumable_update()

        assert resumable is not None
        assert resumable.operation_id == op1.operation_id

    def test_complete_with_total(self, temp_db):
        """complete() should store final book count."""
        from operations import IndexOperation
        import database as db

        operation = IndexOperation.create_build(max_pages=100)
        operation.complete(total_books=5000)

        op_data = db.get_operation(operation.operation_id)
        assert op_data["status"] == "completed"
        checkpoint = op_data["checkpoint_data"]
        assert checkpoint["final_total_books"] == 5000

    def test_fail_operation(self, temp_db):
        """fail() should mark operation as failed."""
        from operations import IndexOperation
        import database as db

        operation = IndexOperation.create_build()
        operation.fail("Too many errors")

        op_data = db.get_operation(operation.operation_id)
        assert op_data["status"] == "failed"
        assert op_data["error_message"] == "Too many errors"


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_get_all_resumable_operations(self, temp_db):
        """get_all_resumable_operations should return summary list."""
        from operations import DownloadOperation, IndexOperation, get_all_resumable_operations

        # Create various operations
        dl_op = DownloadOperation.create(["url1", "url2"], {"author": "Test"})
        dl_op.mark_item_completed("url1")

        idx_op = IndexOperation.create_build(max_pages=50)
        idx_op.save_checkpoint(page=10, total_books_scraped=200)

        resumable = get_all_resumable_operations()

        assert len(resumable) == 2

        # Check download operation
        dl_summary = next(r for r in resumable if r["type"] == "batch_download")
        assert dl_summary["id"] == dl_op.operation_id
        assert dl_summary["context"]["author"] == "Test"
        assert dl_summary["progress"]["pending"] == 1

        # Check index operation
        idx_summary = next(r for r in resumable if r["type"] == "index_build")
        assert idx_summary["id"] == idx_op.operation_id

    def test_cancel_operation(self, temp_db):
        """cancel_operation should mark operation as cancelled."""
        from operations import DownloadOperation, cancel_operation
        import database as db

        operation = DownloadOperation.create(["url1"])
        cancel_operation(operation.operation_id)

        op_data = db.get_operation(operation.operation_id)
        assert op_data["status"] == "cancelled"

    def test_cleanup_stale_operations(self, temp_db):
        """cleanup_stale_operations should mark old running operations as failed."""
        from operations import IndexOperation, cleanup_stale_operations
        import database as db
        from datetime import datetime, timedelta

        # Create an operation
        operation = IndexOperation.create_build()

        # Manually backdate the updated_at to simulate stale operation
        old_time = (datetime.now() - timedelta(hours=48)).isoformat()
        with db.get_connection() as conn:
            conn.execute(
                "UPDATE operations SET updated_at = ? WHERE id = ?",
                (old_time, operation.operation_id)
            )
            conn.commit()

        # Cleanup with 24h threshold
        cleaned = cleanup_stale_operations(max_age_hours=24)

        assert cleaned == 1

        op_data = db.get_operation(operation.operation_id)
        assert op_data["status"] == "failed"
        assert "Stale operation" in op_data["error_message"]
