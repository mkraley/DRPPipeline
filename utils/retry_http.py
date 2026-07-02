"""
HTTP retry helpers with exponential backoff for ADC collection.

Retries transient status codes (403, 429, 5xx). Maps 404/410 to
:class:`SourceNotFoundError` for ``not_found`` handling.
"""

from __future__ import annotations

import time
from typing import Callable, TypeVar

import requests

from utils.Logger import Logger

T = TypeVar("T")

RETRIABLE_HTTP_STATUSES = frozenset({403, 429, 500, 502, 503, 504})
NOT_FOUND_HTTP_STATUSES = frozenset({404, 410})
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 2.0


class SourceNotFoundError(Exception):
    """Raised when the ADC catalog source URL or article metadata is unavailable."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def retry_http_call(
    operation: Callable[[], T],
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BACKOFF_SECONDS,
    operation_label: str = "HTTP request",
) -> T:
    """
    Run ``operation``, retrying retriable HTTP errors with exponential backoff.

    Args:
        operation: Callable that performs one HTTP attempt.
        max_retries: Extra attempts after the first failure.
        base_delay: Base seconds for backoff (doubled each retry).
        operation_label: Text included in log messages.

    Returns:
        The return value of ``operation`` on success.

    Raises:
        SourceNotFoundError: When the response status is 404 or 410.
        requests.HTTPError: When retries are exhausted.
    """
    last_error: requests.HTTPError | None = None
    attempts = max_retries + 1

    for attempt in range(attempts):
        try:
            return operation()
        except requests.HTTPError as exc:
            last_error = exc
            status_code = exc.response.status_code if exc.response is not None else None

            if status_code in NOT_FOUND_HTTP_STATUSES:
                raise SourceNotFoundError(
                    f"{operation_label}: {exc}",
                    status_code=status_code,
                ) from exc

            if status_code not in RETRIABLE_HTTP_STATUSES or attempt >= attempts - 1:
                raise

            wait_seconds = base_delay * (2**attempt)
            Logger.warning(
                "%s returned HTTP %s; retry %s/%s in %.1fs",
                operation_label,
                status_code,
                attempt + 1,
                max_retries,
                wait_seconds,
            )
            time.sleep(wait_seconds)

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"{operation_label} failed without HTTP error")


def download_with_retry(
    download_fn: Callable[[], tuple[int, bool]],
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BACKOFF_SECONDS,
    operation_label: str = "file download",
) -> tuple[int, bool]:
    """
    Retry a download callable that returns ``(bytes_written, success)``.

    Args:
        download_fn: Performs one download attempt.
        max_retries: Extra attempts after the first failure.
        base_delay: Base seconds for exponential backoff.
        operation_label: Text included in log messages.

    Returns:
        Tuple of bytes written and whether the download succeeded.
    """
    attempts = max_retries + 1

    for attempt in range(attempts):
        try:
            written, success = download_fn()
            if success:
                return written, True
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code in NOT_FOUND_HTTP_STATUSES:
                Logger.error("%s: source not found (HTTP %s)", operation_label, status_code)
                return 0, False
            if status_code not in RETRIABLE_HTTP_STATUSES or attempt >= attempts - 1:
                Logger.error("%s failed: %s", operation_label, exc)
                return 0, False
            wait_seconds = base_delay * (2**attempt)
            Logger.warning(
                "%s returned HTTP %s; retry %s/%s in %.1fs",
                operation_label,
                status_code,
                attempt + 1,
                max_retries,
                wait_seconds,
            )
            time.sleep(wait_seconds)
            continue

        if attempt >= attempts - 1:
            return 0, False

        wait_seconds = base_delay * (2**attempt)
        Logger.warning(
            "%s failed; retry %s/%s in %.1fs",
            operation_label,
            attempt + 1,
            max_retries,
            wait_seconds,
        )
        time.sleep(wait_seconds)

    return 0, False
