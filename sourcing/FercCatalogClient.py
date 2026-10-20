"""
HTTP client for the FERC open-data catalog.

Uses ``GET https://api.data.ferc.gov/v1/data-assets/`` with the key in
``Args.ferc_api_key`` (header ``X-Api-Key``).
"""

from __future__ import annotations

from typing import Any

import requests

from utils.Args import Args
from utils.url_utils import requests_verify

DATA_ASSETS_URL = "https://api.data.ferc.gov/v1/data-assets/"
DEFAULT_TIMEOUT_SEC = 60


class FercCatalogClient:
    """Fetch the FERC data-asset catalog, including nested datasets."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    ) -> None:
        """
        Initialize the catalog client.

        Args:
            api_key: FERC API key; defaults to ``Args.ferc_api_key``.
            timeout_sec: HTTP timeout for the catalog request.
        """
        self._api_key = api_key if api_key is not None else _api_key_from_args()
        self._timeout_sec = timeout_sec

    def fetch_data_assets(self) -> list[dict[str, Any]]:
        """
        Return every data asset from the catalog.

        Returns:
            Asset objects. Each may contain a ``data-sets`` list.

        Raises:
            ValueError: When the API key is missing.
            RuntimeError: When the API returns an error or an unexpected body.
        """
        if not self._api_key:
            raise ValueError(
                "FERC catalog sourcing requires ferc_api_key "
                "(sign up at https://data.ferc.gov/developer/gettingstarted/sign-up-form/)."
            )
        try:
            response = requests.get(
                DATA_ASSETS_URL,
                headers={
                    "X-Api-Key": self._api_key,
                    "Accept": "application/json",
                },
                timeout=self._timeout_sec,
                verify=requests_verify(),
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"FERC catalog request failed: {exc}") from exc
        if response.status_code == 429:
            raise RuntimeError(
                "FERC catalog API rate limit exceeded (HTTP 429). "
                "The default limit is 1,000 requests per hour."
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"FERC catalog API HTTP {response.status_code}: {response.text[:300]}"
            )
        return _assets_from_payload(response)

    def close(self) -> None:
        """No persistent resources; provided for fetcher symmetry."""
        return


def _assets_from_payload(response: requests.Response) -> list[dict[str, Any]]:
    """Parse a data-assets response into a list of asset objects."""
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("FERC catalog API returned non-JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("FERC catalog API returned an unexpected JSON type")
    assets = payload.get("data-assets")
    if not isinstance(assets, list):
        raise RuntimeError("FERC catalog API response has no data-assets list")
    return [asset for asset in assets if isinstance(asset, dict)]


def _api_key_from_args() -> str:
    """Return the configured FERC API key, or empty when unset."""
    return str(getattr(Args, "ferc_api_key", None) or "").strip()
