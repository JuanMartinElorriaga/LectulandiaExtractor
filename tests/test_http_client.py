"""
Tests for HTTP client with retry logic.
"""

import pytest
import httpx
import respx
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.infrastructure.http.http_client import HTTPClient, RetryableServerError


class TestHTTPClientBasic:
    """Basic HTTP client tests."""
    
    @respx.mock
    def test_get_success(self):
        """Successful GET request should return response."""
        respx.get("https://example.com/page").mock(
            return_value=httpx.Response(200, text="Hello World")
        )
        
        client = HTTPClient()
        try:
            response = client.get("https://example.com/page")
            assert response.status_code == 200
            assert response.text == "Hello World"
        finally:
            client.close()
    
    @respx.mock
    def test_get_soup_returns_beautifulsoup(self):
        """get_soup should return BeautifulSoup object."""
        html = "<html><body><h1>Title</h1></body></html>"
        respx.get("https://example.com/page").mock(
            return_value=httpx.Response(200, text=html)
        )
        
        client = HTTPClient()
        try:
            soup = client.get_soup("https://example.com/page")
            assert soup.find("h1").text == "Title"
        finally:
            client.close()
    
    @respx.mock
    def test_download_binary(self):
        """download_binary should return bytes."""
        content = b"\x00\x01\x02\x03binary content"
        respx.get("https://example.com/file.epub").mock(
            return_value=httpx.Response(200, content=content)
        )
        
        client = HTTPClient()
        try:
            result = client.download_binary("https://example.com/file.epub")
            assert result == content
        finally:
            client.close()


class TestHTTPClientRetry:
    """Tests for retry behavior."""
    
    @respx.mock
    def test_retry_on_503(self):
        """Should retry on 503 Service Unavailable."""
        route = respx.get("https://example.com/page")
        
        # First two calls return 503, third returns 200
        route.side_effect = [
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(200, text="Success"),
        ]
        
        client = HTTPClient()
        try:
            # Patch sleep to speed up test
            with patch('tenacity.nap.time.sleep'):
                response = client.get("https://example.com/page")
            
            assert response.status_code == 200
            assert route.call_count == 3
        finally:
            client.close()
    
    @respx.mock
    def test_retry_on_502(self):
        """Should retry on 502 Bad Gateway."""
        route = respx.get("https://example.com/page")
        
        route.side_effect = [
            httpx.Response(502),
            httpx.Response(200, text="Success"),
        ]
        
        client = HTTPClient()
        try:
            with patch('tenacity.nap.time.sleep'):
                response = client.get("https://example.com/page")
            
            assert response.status_code == 200
            assert route.call_count == 2
        finally:
            client.close()
    
    @respx.mock
    def test_retry_on_504(self):
        """Should retry on 504 Gateway Timeout."""
        route = respx.get("https://example.com/page")
        
        route.side_effect = [
            httpx.Response(504),
            httpx.Response(200, text="Success"),
        ]
        
        client = HTTPClient()
        try:
            with patch('tenacity.nap.time.sleep'):
                response = client.get("https://example.com/page")
            
            assert response.status_code == 200
        finally:
            client.close()
    
    @respx.mock
    def test_retry_on_429_rate_limit(self):
        """Should retry on 429 Too Many Requests."""
        route = respx.get("https://example.com/page")
        
        route.side_effect = [
            httpx.Response(429),
            httpx.Response(200, text="Success"),
        ]
        
        client = HTTPClient()
        try:
            with patch('tenacity.nap.time.sleep'):
                response = client.get("https://example.com/page")
            
            assert response.status_code == 200
        finally:
            client.close()
    
    @respx.mock
    def test_max_retries_exceeded(self):
        """Should fail after max retries (3)."""
        from tenacity import RetryError
        
        route = respx.get("https://example.com/page")
        
        # All calls return 503
        route.side_effect = [
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(503),
        ]
        
        client = HTTPClient()
        try:
            with patch('tenacity.nap.time.sleep'):
                # tenacity wraps the exception in RetryError
                with pytest.raises((RetryableServerError, RetryError)):
                    client.get("https://example.com/page")
            
            assert route.call_count == 3
        finally:
            client.close()
    
    @respx.mock
    def test_retry_on_timeout(self):
        """Should retry on timeout exception."""
        route = respx.get("https://example.com/page")
        
        route.side_effect = [
            httpx.TimeoutException("Timeout"),
            httpx.Response(200, text="Success"),
        ]
        
        client = HTTPClient()
        try:
            with patch('tenacity.nap.time.sleep'):
                response = client.get("https://example.com/page")
            
            assert response.status_code == 200
        finally:
            client.close()
    
    @respx.mock
    def test_retry_on_connect_error(self):
        """Should retry on connection error."""
        route = respx.get("https://example.com/page")
        
        route.side_effect = [
            httpx.ConnectError("Connection refused"),
            httpx.Response(200, text="Success"),
        ]
        
        client = HTTPClient()
        try:
            with patch('tenacity.nap.time.sleep'):
                response = client.get("https://example.com/page")
            
            assert response.status_code == 200
        finally:
            client.close()


class TestHTTPClientErrors:
    """Tests for error handling."""
    
    @respx.mock
    def test_404_raises_immediately(self):
        """404 errors should not be retried."""
        route = respx.get("https://example.com/notfound")
        route.mock(return_value=httpx.Response(404))
        
        client = HTTPClient()
        try:
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                client.get("https://example.com/notfound")
            
            assert exc_info.value.response.status_code == 404
            assert route.call_count == 1  # No retries
        finally:
            client.close()
    
    @respx.mock
    def test_400_raises_immediately(self):
        """400 Bad Request should not be retried."""
        route = respx.get("https://example.com/bad")
        route.mock(return_value=httpx.Response(400))
        
        client = HTTPClient()
        try:
            with pytest.raises(httpx.HTTPStatusError):
                client.get("https://example.com/bad")
            
            assert route.call_count == 1
        finally:
            client.close()


class TestHTTPClientHeaders:
    """Tests for headers and anti-detection."""
    
    @respx.mock
    def test_has_user_agent(self):
        """Requests should have User-Agent header."""
        route = respx.get("https://example.com/page").mock(
            return_value=httpx.Response(200)
        )
        
        client = HTTPClient()
        try:
            client.get("https://example.com/page")
            
            request = route.calls[0].request
            assert "User-Agent" in request.headers
            assert "Mozilla" in request.headers["User-Agent"]
        finally:
            client.close()
    
    @respx.mock
    def test_has_accept_language(self):
        """Requests should have Accept-Language header."""
        route = respx.get("https://example.com/page").mock(
            return_value=httpx.Response(200)
        )
        
        client = HTTPClient()
        try:
            client.get("https://example.com/page")
            
            request = route.calls[0].request
            assert "Accept-Language" in request.headers
            assert "es" in request.headers["Accept-Language"]
        finally:
            client.close()
    
    @respx.mock
    def test_download_with_referer(self):
        """download_binary should set Referer header when provided."""
        route = respx.get("https://example.com/file.epub").mock(
            return_value=httpx.Response(200, content=b"content")
        )
        
        client = HTTPClient()
        try:
            client.download_binary(
                "https://example.com/file.epub",
                referer="https://example.com/book-page/"
            )
            
            request = route.calls[0].request
            assert "Referer" in request.headers
            assert request.headers["Referer"] == "https://example.com/book-page/"
        finally:
            client.close()


class TestHTTPClientContextManager:
    """Tests for context manager usage."""
    
    @respx.mock
    def test_context_manager(self):
        """Should work as context manager."""
        respx.get("https://example.com/page").mock(
            return_value=httpx.Response(200, text="OK")
        )
        
        with HTTPClient() as client:
            response = client.get("https://example.com/page")
            assert response.status_code == 200
        
        # Client should be closed after context
        # (no explicit assertion needed, just ensure no error)
