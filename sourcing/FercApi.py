"""Shared HTTP helper for the FERC open-data API."""

from __future__ import annotations

from typing import Any

import requests

from utils.Args import Args
from utils.url_utils import requests_verify

API_ROOT = "https://api.data.ferc.gov"
SIGNUP_URL = "https://data.ferc.gov/developer/gettingstarted/sign-up-form/"
DEFAULT_TIMEOUT_SEC = 60


class FercNotFound(Exception):
    """The FERC API returned HTTP 404 for a dataset resource."""


def ferc_api_key() -> str:
    """Return the configured FERC API key, or empty when unset."""
    return str(getattr(Args, "ferc_api_key", None) or "").strip()


def ferc_get_json(url: str, api_key: str, *, timeout_sec: int = DEFAULT_TIMEOUT_SEC) -> Any:
    """
    GET a FERC API URL and return parsed JSON.

    Args:
        url: Absolute API URL.
        api_key: Value for the ``X-Api-Key`` header.
        timeout_sec: HTTP timeout.

    Returns:
        Parsed JSON body.

    Raises:
        ValueError: When ``api_key`` is empty.
        FercNotFound: When the API returns HTTP 404.
        RuntimeError: When the request fails or the body is not JSON.
    """
    if not api_key:
        raise ValueError(
            "FERC API requests require ferc_api_key "
            f"(sign up at {SIGNUP_URL})."
        )
    try:
        response = requests.get(
            url,
            headers={"X-Api-Key": api_key, "Accept": "application/json"},
            timeout=timeout_sec,
            verify=requests_verify(),
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"FERC API request failed: {exc}") from exc
    if response.status_code == 404:
        raise FercNotFound(url)
    if response.status_code == 429:
        raise RuntimeError(
            "FERC API rate limit exceeded (HTTP 429). "
            "The default limit is 1,000 requests per hour."
        )
    if response.status_code >= 400:
        raise RuntimeError(f"FERC API HTTP {response.status_code}: {response.text[:300]}")
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError("FERC API returned non-JSON") from exc
