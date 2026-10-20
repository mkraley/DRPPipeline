"""Read the long-form dictionary embedded in a FERC dataset page."""

from __future__ import annotations

import json
from typing import Any

import requests

from utils.url_utils import requests_verify

_NEXT_DATA = '<script id="__NEXT_DATA__"'


def fetch_landing_html(url: str, *, timeout_sec: int = 60) -> str:
    """
    Download the dataset landing page HTML.

    Args:
        url: Dataset landing page.
        timeout_sec: HTTP timeout.

    Returns:
        Response body text.

    Raises:
        RuntimeError: When the page cannot be fetched.
    """
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "DRPPipeline", "Accept": "text/html"},
            timeout=timeout_sec,
            verify=requests_verify(),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"FERC landing page request failed: {exc}") from exc
    return response.text


def parse_embedded_dictionary(html: str) -> list[dict[str, Any]] | None:
    """
    Return the page's embedded ``dataDict``, when it has rows.

    Args:
        html: Landing page HTML.

    Returns:
        Dictionary rows, or None when the page has no dictionary.
    """
    payload = _next_data(html)
    if payload is None:
        return None
    props = payload.get("props", {}).get("pageProps", {})
    if not isinstance(props, dict):
        return None
    rows = props.get("dataDict")
    if not isinstance(rows, list):
        return None
    dictionaries = [row for row in rows if isinstance(row, dict)]
    return dictionaries or None


def _next_data(html: str) -> dict[str, Any] | None:
    """Parse the Next.js ``__NEXT_DATA__`` object."""
    start = html.find(_NEXT_DATA)
    if start < 0:
        return None
    start = html.find(">", start) + 1
    end = html.find("</script>", start)
    if end < 0:
        return None
    try:
        payload = json.loads(html[start:end])
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload
