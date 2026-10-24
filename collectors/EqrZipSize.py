"""Read the byte size of an EQR quarterly zip without downloading it."""

from __future__ import annotations

from collections.abc import Callable

import requests

from utils.url_utils import BROWSER_HEADERS, requests_verify

RangeGet = Callable[..., requests.Response]


def zip_content_length(url: str, *, getter: RangeGet | None = None) -> int:
    """
    Return the archive size from a one-byte range response.

    Args:
        url: Quarterly CSV zip URL.
        getter: ``requests.get`` replacement for tests.

    Returns:
        Size in bytes.

    Raises:
        RuntimeError: When the response does not report a size.
    """
    get = getter or requests.get
    response = get(
        url,
        headers={**BROWSER_HEADERS, "Range": "bytes=0-0"},
        timeout=60,
        verify=requests_verify(),
        stream=True,
    )
    try:
        return _size_from_response(response, url)
    finally:
        response.close()


def _size_from_response(response: requests.Response, url: str) -> int:
    """Read Content-Range or a full Content-Length."""
    if response.status_code not in {200, 206}:
        raise RuntimeError(f"HTTP {response.status_code} for {url}")
    header = response.headers.get("Content-Range", "")
    total = header.rsplit("/", 1)[-1] if "/" in header else ""
    if total.isdigit():
        return int(total)
    length = response.headers.get("Content-Length", "")
    if length.isdigit() and int(length) > 1000:
        return int(length)
    raise RuntimeError(f"No size reported for {url}")
