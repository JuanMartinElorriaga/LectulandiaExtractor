"""
Tests for the download_tracker module.
"""

import pytest


class TestDownloadTracker:
    """Tests for DownloadTracker class."""

    def test_is_downloaded_false_initially(self, temp_db):
        """New slugs should not be marked as downloaded."""
        from download_tracker import DownloadTracker

        tracker = DownloadTracker()
        assert tracker.is_downloaded("some-new-book") is False

    def test_record_download_marks_as_downloaded(self, temp_db):
        """Recording a download should mark the slug as downloaded."""
        from download_tracker import DownloadTracker

        tracker = DownloadTracker()

        tracker.record_download(
            slug="my-book",
            title="My Book",
            author="Author Name",
            source_url="https://example.com/book/my-book/",
            file_path="Author Name/My Book/My Book.epub",
            file_size=1234567
        )

        assert tracker.is_downloaded("my-book") is True

    def test_record_download_returns_id(self, temp_db):
        """record_download should return the record ID."""
        from download_tracker import DownloadTracker

        tracker = DownloadTracker()

        record_id = tracker.record_download(
            slug="my-book",
            title="My Book",
            author="Author Name",
            source_url="https://example.com/book/my-book/",
            file_path="Author Name/My Book/My Book.epub",
            file_size=1234567
        )

        assert record_id is not None
        assert isinstance(record_id, int)
        assert record_id > 0

    def test_get_download_status(self, temp_db):
        """get_download_status should return full record."""
        from download_tracker import DownloadTracker

        tracker = DownloadTracker()

        tracker.record_download(
            slug="my-book",
            title="My Book",
            author="Author Name",
            source_url="https://example.com/book/my-book/",
            file_path="Author Name/My Book/My Book.epub",
            file_size=1234567,
            download_mode="author"
        )

        status = tracker.get_download_status("my-book")

        assert status is not None
        assert status["slug"] == "my-book"
        assert status["title"] == "My Book"
        assert status["author"] == "Author Name"
        assert status["status"] == "completed"
        assert status["download_mode"] == "author"

    def test_get_download_status_not_found(self, temp_db):
        """get_download_status should return None for unknown slugs."""
        from download_tracker import DownloadTracker

        tracker = DownloadTracker()
        status = tracker.get_download_status("nonexistent")

        assert status is None

    def test_record_failure(self, temp_db):
        """record_failure should create a failed download record."""
        from download_tracker import DownloadTracker

        tracker = DownloadTracker()

        tracker.record_failure(
            slug="failed-book",
            source_url="https://example.com/book/failed-book/",
            error="Connection timeout"
        )

        # Failed books should NOT be marked as downloaded
        assert tracker.is_downloaded("failed-book") is False

        # But should have a record
        status = tracker.get_download_status("failed-book")
        assert status is not None
        assert status["status"] == "failed"
        assert status["error_message"] == "Connection timeout"

    def test_record_skip(self, temp_db):
        """record_skip should create a skipped download record."""
        from download_tracker import DownloadTracker

        tracker = DownloadTracker()

        tracker.record_skip(
            slug="skipped-book",
            source_url="https://example.com/book/skipped-book/",
            reason="duplicate"
        )

        # Skipped books should NOT be marked as downloaded
        assert tracker.is_downloaded("skipped-book") is False

        status = tracker.get_download_status("skipped-book")
        assert status is not None
        assert status["status"] == "skipped"

    def test_get_downloaded_slugs(self, temp_db):
        """get_downloaded_slugs should return set of completed downloads."""
        from download_tracker import DownloadTracker

        tracker = DownloadTracker()

        # Record some downloads
        tracker.record_download(
            slug="book-1", title="Book 1", author="Author",
            source_url="url1", file_path="path1", file_size=100
        )
        tracker.record_download(
            slug="book-2", title="Book 2", author="Author",
            source_url="url2", file_path="path2", file_size=200
        )
        tracker.record_failure(slug="book-3", source_url="url3", error="Error")

        slugs = tracker.get_downloaded_slugs()

        assert isinstance(slugs, set)
        assert "book-1" in slugs
        assert "book-2" in slugs
        assert "book-3" not in slugs  # Failed, not downloaded

    def test_get_stats(self, temp_db):
        """get_stats should return correct statistics."""
        from download_tracker import DownloadTracker
        import database as db

        # Add some catalog books for reference
        db.insert_books([
            {"title": "Book 1", "slug": "book-1", "author": "A", "url": "u1"},
            {"title": "Book 2", "slug": "book-2", "author": "A", "url": "u2"},
            {"title": "Book 3", "slug": "book-3", "author": "A", "url": "u3"},
        ])

        tracker = DownloadTracker()

        tracker.record_download(
            slug="book-1", title="Book 1", author="A",
            source_url="url1", file_path="path1", file_size=100
        )
        tracker.record_failure(slug="book-2", source_url="url2", error="Error")
        tracker.record_skip(slug="book-3", source_url="url3", reason="dup")

        stats = tracker.get_stats()

        assert stats["downloaded"] == 1
        assert stats["failed"] == 1
        assert stats["skipped"] == 1
        assert stats["total_attempted"] == 3
        # Success rate: (1 downloaded + 1 skipped) / 3 processed = 66.67%
        assert stats["percentage"] == pytest.approx(66.67, rel=0.1)


class TestDownloadTrackerSlugExtraction:
    """Tests for slug extraction from URLs."""

    def test_extract_slug_from_book_url(self):
        """Should extract slug from /book/ URLs."""
        from download_tracker import DownloadTracker

        slug = DownloadTracker.extract_slug_from_url(
            "https://ww3.lectulandia.com/book/cien-anos-de-soledad/"
        )
        assert slug == "cien-anos-de-soledad"

    def test_extract_slug_from_download_url(self):
        """Should extract slug from download.php URLs."""
        from download_tracker import DownloadTracker

        slug = DownloadTracker.extract_slug_from_url(
            "https://www.lectulandia.com/download.php?t=1&slug=my-book"
        )
        assert slug == "my-book"

    def test_extract_slug_returns_none_for_invalid(self):
        """Should return None for unrecognized URL formats."""
        from download_tracker import DownloadTracker

        slug = DownloadTracker.extract_slug_from_url(
            "https://example.com/random/path/"
        )
        assert slug is None


class TestDownloadTrackerNameToSlug:
    """Tests for name to slug conversion."""

    def test_name_to_slug_basic(self):
        """Should convert names to slugs."""
        from download_tracker import DownloadTracker

        slug = DownloadTracker._name_to_slug("Cien Años de Soledad")
        assert slug == "cien-anos-de-soledad"

    def test_name_to_slug_special_chars(self):
        """Should handle special characters."""
        from download_tracker import DownloadTracker

        slug = DownloadTracker._name_to_slug("El Niño & La Niña (2024)")
        assert slug == "el-nino-la-nina-2024"

    def test_name_to_slug_multiple_spaces(self):
        """Should handle multiple spaces."""
        from download_tracker import DownloadTracker

        slug = DownloadTracker._name_to_slug("Title   With   Spaces")
        assert slug == "title-with-spaces"


class TestSyncWithFilesystem:
    """Tests for filesystem sync functionality."""

    def test_sync_with_empty_folder(self, temp_db, tmp_path):
        """Sync with empty folder should return zeros."""
        from download_tracker import DownloadTracker

        tracker = DownloadTracker()
        result = tracker.sync_with_filesystem(str(tmp_path))

        assert result["found"] == 0
        assert result["added"] == 0
        assert result["already_tracked"] == 0

    def test_sync_with_nonexistent_folder(self, temp_db, tmp_path):
        """Sync with nonexistent folder should return zeros."""
        from download_tracker import DownloadTracker

        tracker = DownloadTracker()
        result = tracker.sync_with_filesystem(str(tmp_path / "nonexistent"))

        assert result["found"] == 0
        assert result["added"] == 0
        assert result["already_tracked"] == 0

    def test_sync_finds_epubs(self, temp_db, tmp_path, valid_epub):
        """Sync should find and register EPUB files."""
        from download_tracker import DownloadTracker
        import shutil

        # Create Author/Book structure
        author_dir = tmp_path / "Author Name"
        author_dir.mkdir()
        dest_epub = author_dir / "My Book.epub"
        shutil.copy(valid_epub, dest_epub)

        tracker = DownloadTracker()
        result = tracker.sync_with_filesystem(str(tmp_path))

        assert result["found"] == 1
        assert result["added"] == 1
        assert result["already_tracked"] == 0

    def test_sync_skips_already_tracked(self, temp_db, tmp_path, valid_epub):
        """Sync should skip already tracked books."""
        from download_tracker import DownloadTracker
        import shutil

        # Create Author/Book structure
        author_dir = tmp_path / "Author Name"
        author_dir.mkdir()
        dest_epub = author_dir / "My Book.epub"
        shutil.copy(valid_epub, dest_epub)

        tracker = DownloadTracker()

        # First sync
        result1 = tracker.sync_with_filesystem(str(tmp_path))
        assert result1["added"] == 1

        # Second sync - should skip
        result2 = tracker.sync_with_filesystem(str(tmp_path))
        assert result2["found"] == 1
        assert result2["added"] == 0
        assert result2["already_tracked"] == 1
