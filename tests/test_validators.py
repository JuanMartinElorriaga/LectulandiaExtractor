"""
Tests for validators module (security-critical functions).
"""

import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.utils.validators import sanitize_filename, sanitize_path, validate_epub


class TestSanitizeFilename:
    """Tests for sanitize_filename function."""
    
    def test_removes_dangerous_chars(self):
        """Should remove < > : " / \\ | ? * characters."""
        dangerous = 'file<>name:test"path/back\\pipe|quest?star*'
        result = sanitize_filename(dangerous)
        
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert '"' not in result
        assert "/" not in result
        assert "\\" not in result
        assert "|" not in result
        assert "?" not in result
        assert "*" not in result
    
    def test_prevents_path_traversal(self):
        """Should remove .. path traversal patterns."""
        malicious = "../../etc/passwd"
        result = sanitize_filename(malicious)
        
        assert ".." not in result
        assert result == "etcpasswd"
    
    def test_normalizes_multiple_spaces(self):
        """Should collapse multiple spaces to single space."""
        spacy = "too    many     spaces"
        result = sanitize_filename(spacy)
        
        assert "  " not in result
        assert result == "too many spaces"
    
    def test_strips_whitespace(self):
        """Should strip leading and trailing whitespace."""
        padded = "  filename  "
        result = sanitize_filename(padded)
        
        assert result == "filename"
    
    def test_preserves_normal_characters(self):
        """Should preserve normal alphanumeric and safe characters."""
        normal = "My Book Title - Author Name (2024)"
        result = sanitize_filename(normal)
        
        assert result == normal
    
    def test_handles_unicode(self):
        """Should preserve unicode characters."""
        unicode_name = "Cien años de soledad - García Márquez"
        result = sanitize_filename(unicode_name)
        
        assert "años" in result
        assert "García" in result
    
    def test_empty_string(self):
        """Should handle empty string."""
        result = sanitize_filename("")
        assert result == ""
    
    def test_only_dangerous_chars(self):
        """Should return empty for string with only dangerous chars."""
        result = sanitize_filename("<>:\"")
        assert result == ""


class TestSanitizePath:
    """Tests for sanitize_path function (path traversal prevention)."""
    
    def test_creates_valid_path(self, tmp_path):
        """Should create a valid path within base."""
        result = sanitize_path(tmp_path, "author", "book title")
        
        assert result.parent.name == "author"
        assert result.name == "book title"
        assert str(tmp_path) in str(result)
    
    def test_stays_within_base(self, tmp_path):
        """Path should remain within base_path."""
        result = sanitize_path(tmp_path, "subdir", "file")
        
        # Should be resolvable relative to base
        assert result.is_relative_to(tmp_path.resolve())
    
    def test_handles_traversal_attempt(self, tmp_path):
        """Path traversal attempts should be sanitized."""
        # The sanitize_path function sanitizes components first,
        # so traversal attempts are neutralized before they can escape
        result = sanitize_path(tmp_path, "..", "..", "etc", "passwd")
        
        # After sanitization, ".." becomes "" and is removed
        # The path should still be within tmp_path
        assert result.is_relative_to(tmp_path.resolve())
    
    def test_sanitizes_components(self, tmp_path):
        """Should sanitize each path component."""
        result = sanitize_path(tmp_path, "author:name", "book<title>")
        
        assert ":" not in str(result)
        assert "<" not in str(result)
        assert ">" not in str(result)
    
    def test_handles_unicode_paths(self, tmp_path):
        """Should handle unicode in path components."""
        result = sanitize_path(tmp_path, "García Márquez", "Cien años")
        
        assert "García Márquez" in str(result)
        assert "Cien años" in str(result)
    
    def test_multiple_components(self, tmp_path):
        """Should handle multiple path components."""
        result = sanitize_path(tmp_path, "genre", "author", "book", "chapter")
        
        parts = result.parts
        assert "genre" in parts
        assert "author" in parts
        assert "book" in parts
        assert "chapter" in parts


class TestValidateEpub:
    """Tests for EPUB validation."""
    
    def test_valid_epub(self, valid_epub):
        """Valid EPUB should return True."""
        result = validate_epub(valid_epub)
        assert result is True
    
    def test_invalid_mimetype(self, invalid_epub_mimetype):
        """EPUB with wrong mimetype should return False."""
        result = validate_epub(invalid_epub_mimetype)
        assert result is False
    
    def test_missing_mimetype(self, invalid_epub_no_mimetype):
        """EPUB without mimetype file should return False."""
        result = validate_epub(invalid_epub_no_mimetype)
        assert result is False
    
    def test_corrupted_file(self, corrupted_file):
        """Corrupted (non-ZIP) file should return False."""
        result = validate_epub(corrupted_file)
        assert result is False
    
    def test_nonexistent_file(self, tmp_path):
        """Non-existent file should return False."""
        nonexistent = tmp_path / "does_not_exist.epub"
        result = validate_epub(nonexistent)
        assert result is False
