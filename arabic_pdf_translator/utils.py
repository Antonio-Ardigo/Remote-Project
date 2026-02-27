"""
Utility functions for the Arabic PDF Translation pipeline.
"""

import logging
import re
import time
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger(__name__)


def setup_logging(level: int = logging.INFO) -> None:
    """Configure logging for the pipeline."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(name)-30s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _is_retryable_error(exc: Exception) -> bool:
    """Check if an exception represents a retryable error (not a 4xx client error)."""
    # Anthropic SDK errors
    try:
        import anthropic
        if isinstance(exc, anthropic.BadRequestError):
            return False
        if isinstance(exc, anthropic.AuthenticationError):
            return False
        if isinstance(exc, anthropic.PermissionDeniedError):
            return False
        if isinstance(exc, anthropic.NotFoundError):
            return False
        if isinstance(exc, anthropic.UnprocessableEntityError):
            return False
    except ImportError:
        pass

    # OpenAI SDK errors
    try:
        import openai
        if isinstance(exc, openai.BadRequestError):
            return False
        if isinstance(exc, openai.AuthenticationError):
            return False
        if isinstance(exc, openai.PermissionDeniedError):
            return False
        if isinstance(exc, openai.NotFoundError):
            return False
        if isinstance(exc, openai.UnprocessableEntityError):
            return False
    except ImportError:
        pass

    # HTTP response errors (httpx, requests)
    status_code = getattr(exc, 'status_code', None) or getattr(
        getattr(exc, 'response', None), 'status_code', None
    )
    if status_code is not None and 400 <= status_code < 500:
        return False

    return True


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exceptions: tuple = (Exception,),
) -> Callable:
    """Decorator for retrying API calls with exponential backoff.

    Client errors (4xx) are raised immediately without retrying since
    they indicate a problem with the request that won't be fixed by retrying.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if not _is_retryable_error(e):
                        logger.error(
                            "%s failed with non-retryable error: %s",
                            func.__name__,
                            str(e),
                        )
                        raise
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        logger.warning(
                            "Attempt %d/%d for %s failed: %s. Retrying in %.1fs",
                            attempt + 1,
                            max_retries + 1,
                            func.__name__,
                            str(e),
                            delay,
                        )
                        time.sleep(delay)
            raise last_exception  # type: ignore[misc]

        return wrapper

    return decorator


def chunk_text(text: str, max_chars: int = 3000, overlap: int = 200) -> list[str]:
    """
    Split text into chunks respecting sentence boundaries.

    Arabic sentence endings: . (period), ، (Arabic comma),
    。(ideographic period used in some contexts), newlines.
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0

    # Arabic and general sentence-ending patterns
    sentence_end_pattern = re.compile(r'[.!?،؟\n]\s*')

    while start < len(text):
        end = start + max_chars

        if end >= len(text):
            chunks.append(text[start:].strip())
            break

        # Find the last sentence boundary within the chunk
        chunk_text_segment = text[start:end]
        matches = list(sentence_end_pattern.finditer(chunk_text_segment))

        if matches:
            # Split at the last sentence boundary
            last_match = matches[-1]
            split_pos = start + last_match.end()
        else:
            # No sentence boundary found — split at last whitespace
            last_space = chunk_text_segment.rfind(' ')
            if last_space > 0:
                split_pos = start + last_space
            else:
                split_pos = end

        chunks.append(text[start:split_pos].strip())
        # Move forward, applying overlap by stepping back slightly
        start = split_pos

    return [c for c in chunks if c]


def is_arabic(text: str) -> bool:
    """Check if text contains Arabic characters."""
    arabic_pattern = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]')
    arabic_chars = len(arabic_pattern.findall(text))
    total_alpha = sum(1 for c in text if c.isalpha())
    if total_alpha == 0:
        return False
    return (arabic_chars / total_alpha) > 0.3


def normalize_arabic(text: str) -> str:
    """
    Normalize Arabic text for comparison purposes.
    Removes diacritics (tashkeel) and normalizes alef/yaa variants.
    """
    # Remove tashkeel (diacritical marks)
    tashkeel = re.compile(r'[\u0617-\u061A\u064B-\u0652\u0670]')
    text = tashkeel.sub('', text)

    # Normalize alef variants → plain alef
    text = re.sub(r'[\u0622\u0623\u0625\u0671]', '\u0627', text)

    # Normalize taa marbuta → haa
    text = text.replace('\u0629', '\u0647')

    # Normalize alef maqsura → yaa
    text = text.replace('\u0649', '\u064A')

    return text


def calculate_text_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity between two texts using word-level Jaccard coefficient.
    """
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())

    if not words1 and not words2:
        return 1.0
    if not words1 or not words2:
        return 0.0

    intersection = words1 & words2
    union = words1 | words2

    return len(intersection) / len(union)
