"""Exponential backoff retry decorator for Google API calls."""

from __future__ import annotations

import functools
import logging
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

from googleapiclient.errors import HttpError

from gbridge.config.defaults import BASE_RETRY_DELAY_SECONDS, MAX_RETRIES

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# HTTP status codes that are safe to retry (transient errors only)
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503})


def retry_on_api_error(
    max_retries: int = MAX_RETRIES,
    base_delay: float = BASE_RETRY_DELAY_SECONDS,
) -> Callable[[F], F]:
    """Decorator: retry a function on transient Google API errors.

    Uses exponential backoff with jitter.  Only retries on 429 / 5xx
    status codes — never on auth errors (401/403) or client errors (4xx).
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except HttpError as exc:
                    status = exc.resp.status if exc.resp else 0
                    if status not in _RETRYABLE_STATUS_CODES or attempt == max_retries:
                        raise
                    last_exc = exc
                    delay = base_delay * (2**attempt) + random.uniform(0, 0.5)  # noqa: S311
                    logger.warning(
                        "API call %s failed (HTTP %d), retrying in %.1fs (attempt %d/%d)",
                        func.__name__,
                        status,
                        delay,
                        attempt + 1,
                        max_retries,
                    )
                    time.sleep(delay)

            # Should not reach here, but satisfy type checker
            if last_exc is not None:
                raise last_exc  # pragma: no cover

        return wrapper  # type: ignore[return-value]

    return decorator
