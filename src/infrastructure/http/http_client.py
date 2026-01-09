"""HTTP client with automatic retry and rate limiting."""
import httpx
import random
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from loguru import logger
from bs4 import BeautifulSoup
from config.settings import settings


class RetryableServerError(Exception):
    """Custom exception for server errors that should be retried (429, 502, 503, 504)."""
    pass


class HTTPClient:
    """
    HTTP client with automatic retry, rate limiting, and anti-detection features.

    Features:
    - Automatic retry with exponential backoff
    - Random User-Agent rotation
    - Realistic browser headers
    - HTTP/2 support
    - Proxy support
    """

    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    ]

    def __init__(self, proxy: str = None):
        """
        Initialize HTTP client.

        Args:
            proxy: Optional proxy URL (e.g., "http://proxy.example.com:8080")
        """
        headers = {
            'User-Agent': random.choice(self.USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }

        self.client = httpx.Client(
            headers=headers,
            proxy=proxy,
            timeout=httpx.Timeout(
                timeout=settings.REQUEST_TIMEOUT,
                connect=settings.CONNECT_TIMEOUT
            ),
            follow_redirects=True,
            http2=False,  # Disable HTTP/2 to avoid h2 dependency
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.RemoteProtocolError,
            RetryableServerError,
        )),
        before_sleep=lambda retry_state: logger.warning(
            f"Retry {retry_state.attempt_number}/3 después de error: {retry_state.outcome.exception()}"
        )
    )
    def get(self, url: str, **kwargs) -> httpx.Response:
        """
        GET request with automatic retry.

        Args:
            url: URL to fetch
            **kwargs: Additional arguments passed to httpx.Client.get()

        Returns:
            httpx.Response object

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx status codes (after retries)
        """
        response = self.client.get(url, **kwargs)

        # Retry on rate limiting and temporary server errors
        if response.status_code in (429, 502, 503, 504):
            logger.warning(f"Error temporal {response.status_code} en {url}, reintentando...")
            raise RetryableServerError(
                f"Server returned {response.status_code} for {url}"
            )

        response.raise_for_status()
        return response

    def get_soup(self, url: str, parser: str = None) -> BeautifulSoup:
        """
        GET request + parse HTML with BeautifulSoup.

        Args:
            url: URL to fetch
            parser: HTML parser to use (default: from settings)

        Returns:
            BeautifulSoup object
        """
        if parser is None:
            parser = settings.HTML_PARSER

        response = self.get(url)
        return BeautifulSoup(response.text, parser)

    def download_binary(self, url: str, timeout: int = None, referer: str = None) -> bytes:
        """
        Download binary content (e.g., EPUB file).

        Args:
            url: URL to download from
            timeout: Optional custom timeout in seconds
            referer: Optional Referer header for anti-bot protection

        Returns:
            Binary content as bytes
        """
        if timeout:
            # Temporarily override timeout for large downloads
            original_timeout = self.client.timeout
            self.client.timeout = httpx.Timeout(timeout)

        try:
            headers = {}
            if referer:
                headers['Referer'] = referer

            response = self.get(url, headers=headers)
            return response.content
        finally:
            if timeout:
                self.client.timeout = original_timeout

    def close(self):
        """Close the HTTP client and release resources."""
        self.client.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, *args):
        """Context manager exit - closes client."""
        self.close()
