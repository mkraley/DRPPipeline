"""
HTTP client for Social Security Administration datasets in the Data.gov catalog.

Uses the GSA Catalog API (not the retired CKAN action API). Requires an
api.data.gov key in ``Args.gsa_api_key``.
"""

from __future__ import annotations

from typing import Any

import requests

from utils.Args import Args
from utils.url_utils import requests_verify

GSA_SEARCH_URL = "https://api.gsa.gov/technology/datagov/v4/search"
DEFAULT_ORG_SLUG = "ssa"
DEFAULT_PER_PAGE = 50
DEFAULT_TIMEOUT_SEC = 60


class SsaCatalogClient:
    """Fetch paginated SSA dataset search results from the GSA Catalog API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        org_slug: str | None = None,
        per_page: int = DEFAULT_PER_PAGE,
        timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    ) -> None:
        """
        Initialize the catalog client.

        Args:
            api_key: api.data.gov key; defaults to ``Args.gsa_api_key``.
            org_slug: Organization slug; defaults to ``ssa``.
            per_page: Results per search page.
            timeout_sec: HTTP timeout per request.
        """
        self._api_key = api_key if api_key is not None else _api_key_from_args()
        self._org_slug = org_slug or DEFAULT_ORG_SLUG
        self._per_page = per_page
        self._timeout_sec = timeout_sec

    def fetch_search_page(self, *, after: str | None = None) -> dict[str, Any]:
        """
        Fetch one search page for the SSA organization.

        Args:
            after: Cursor from a previous response, or None for the first page.

        Returns:
            Parsed JSON object with ``results`` and optional ``after``.

        Raises:
            ValueError: When the API key is missing.
            RuntimeError: When the API returns an error status or invalid JSON.
        """
        if not self._api_key:
            raise ValueError(
                "SSA catalog sourcing requires gsa_api_key "
                "(free key from https://api.data.gov/)."
            )
        params: dict[str, str | int] = {
            "org_slug": self._org_slug,
            "per_page": self._per_page,
            "sort": "last_harvested_date",
        }
        if after:
            params["after"] = after
        try:
            response = requests.get(
                GSA_SEARCH_URL,
                headers={
                    "X-Api-Key": self._api_key,
                    "Accept": "application/json",
                },
                params=params,
                timeout=self._timeout_sec,
                verify=requests_verify(),
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"SSA catalog request failed: {exc}") from exc
        if response.status_code == 429:
            raise RuntimeError(
                "SSA catalog API rate limit exceeded (HTTP 429). "
                "Wait and retry, or use a personal api.data.gov key."
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"SSA catalog API HTTP {response.status_code}: {response.text[:300]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("SSA catalog API returned non-JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("SSA catalog API returned an unexpected JSON type")
        return payload

    def close(self) -> None:
        """No persistent resources; provided for fetcher symmetry."""
        return


def _api_key_from_args() -> str:
    """Return the configured GSA API key, or empty when unset."""
    return str(getattr(Args, "gsa_api_key", None) or "").strip()
