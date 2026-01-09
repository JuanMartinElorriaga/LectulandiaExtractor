"""Rate limiting and delay utilities."""
import random
import time
from loguru import logger
from config.settings import settings


def smart_delay(min_seconds: float = None, max_seconds: float = None):
    """
    Random delay between min and max to avoid rate limiting detection.

    Uses configured defaults from settings if not specified.

    Args:
        min_seconds: Minimum delay (default: from settings)
        max_seconds: Maximum delay (default: from settings)

    Examples:
        >>> smart_delay(1.0, 3.0)  # Wait 1-3 seconds randomly
        >>> smart_delay()  # Use configured defaults
    """
    if min_seconds is None:
        min_seconds = settings.REQUEST_DELAY_MIN
    if max_seconds is None:
        max_seconds = settings.REQUEST_DELAY_MAX

    delay = random.uniform(min_seconds, max_seconds)
    logger.debug(f"Esperando {delay:.2f}s antes del siguiente request")
    time.sleep(delay)
