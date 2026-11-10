"""
HTTP client for the EPA EDG Clip and Ship Hub Search API.

Lists every public item in the site catalog at
``https://edg-epa.hub.arcgis.com/search``.
"""

from __future__ import annotations

from typing import Any

import requests

from utils.Args import Args
from utils.url_utils import requests_verify

DEFAULT_ITEMS_URL = (
    "https://edg-epa.hub.arcgis.com/api/search/v1/collections/all/items"
)
DEFAULT_PAGE_SIZE = 100
DEFAULT_TIMEOUT_SEC = 60


class EpaHubCatalogClient:
    """Fetch paginated items from the EDG Clip and Ship search catalog."""

    def __init__(
        self,
        *,
        items_url: str | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    ) -> None:
        """
        Initialize the catalog client.

        Args:
            items_url: Items endpoint. Defaults to ``Args.epa_hub_items_url``
                or the Clip and Ship ``all`` collection.
            page_size: Items requested per page.
            timeout_sec: HTTP timeout per request.

        Raises:
            ValueError: When the items URL or page size is invalid.
        """
        self._items_url = _resolve_items_url(items_url)
        if page_size < 1:
            raise ValueError("page_size must be at least 1")
        self._page_size = page_size
        self._timeout_sec = timeout_sec

    def fetch_items(self) -> list[dict[str, Any]]:
        """
        Return every feature in the catalog.

        Returns:
            GeoJSON features from the items endpoint.

        Raises:
            RuntimeError: When a page request fails.
        """
        items: list[dict[str, Any]] = []
        startindex = 1
        while True:
            page = self.fetch_page(startindex)
            features = _features_from_page(page)
            items.extend(features)
            if not features:
                break
            startindex += len(features)
            if _page_is_complete(page, startindex, len(features), self._page_size):
                break
        return items

    def fetch_page(self, startindex: int) -> dict[str, Any]:
        """
        Fetch one items page.

        Args:
            startindex: 1-based index of the first item on the page.

        Returns:
            Parsed GeoJSON feature collection.

        Raises:
            RuntimeError: When the API returns an error or invalid JSON.
        """
        try:
            response = requests.get(
                self._items_url,
                params={"limit": self._page_size, "startindex": startindex},
                headers={"Accept": "application/geo+json"},
                timeout=self._timeout_sec,
                verify=requests_verify(),
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"EDG Clip and Ship request failed: {exc}") from exc
        return _payload_from_response(response)

    def close(self) -> None:
        """No persistent resources; provided for fetcher symmetry."""
        return


def _resolve_items_url(items_url: str | None) -> str:
    """Return the items endpoint, from the argument, config, or the default."""
    if items_url is not None and items_url.strip():
        return items_url.strip()
    configured = str(getattr(Args, "epa_hub_items_url", None) or "").strip()
    if configured:
        return configured
    return DEFAULT_ITEMS_URL


def _features_from_page(page: dict[str, Any]) -> list[dict[str, Any]]:
    """Return feature objects from one items page."""
    features = page.get("features")
    if not isinstance(features, list):
        raise RuntimeError("EDG Clip and Ship response has no features list")
    return [feature for feature in features if isinstance(feature, dict)]


def _page_is_complete(
    page: dict[str, Any],
    next_index: int,
    page_count: int,
    page_size: int,
) -> bool:
    """Return True when no further items page should be requested."""
    matched = page.get("numberMatched")
    if isinstance(matched, int):
        return next_index > matched
    return page_count < page_size


def _payload_from_response(response: requests.Response) -> dict[str, Any]:
    """Parse a successful items response."""
    if response.status_code == 429:
        raise RuntimeError(
            "EDG Clip and Ship API rate limit exceeded (HTTP 429). Wait and retry."
        )
    if response.status_code >= 400:
        raise RuntimeError(
            f"EDG Clip and Ship API HTTP {response.status_code}: {response.text[:300]}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("EDG Clip and Ship API returned non-JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("EDG Clip and Ship API returned an unexpected JSON type")
    return payload
