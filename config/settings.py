"""Centralized configuration for LectulandiaExtractor."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # URLs
    LECTULANDIA_BASE_URL: str = "https://ww3.lectulandia.com"
    ANTUPLOAD_BASE_URL: str = "https://www.antupload.com"

    # Rate Limiting
    REQUEST_DELAY_MIN: float = 2.0
    REQUEST_DELAY_MAX: float = 5.0
    MAX_RETRIES: int = 3
    RETRY_BACKOFF_FACTOR: float = 2.0

    # Fuzzy Matching Thresholds
    AUTHOR_MATCH_THRESHOLD: int = 90
    BOOK_MATCH_THRESHOLD: int = 90

    # Timeouts (in seconds)
    DOWNLOAD_TIMEOUT: int = 180
    REQUEST_TIMEOUT: int = 30
    CONNECT_TIMEOUT: int = 10

    # Default Paths
    DEFAULT_DOWNLOAD_FOLDER: str = "./downloads"
    DEFAULT_CALIBRE_LIBRARY: str = "/Users/jelorriaga/Documents/Libros"

    # Limits
    MAX_PAGINATION_DEPTH: int = 50  # Prevent infinite recursion

    # Parser
    HTML_PARSER: str = "lxml"  # Faster than html.parser

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Singleton instance
settings = Settings()
