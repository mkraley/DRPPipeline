"""
HTTP client for the FERC open-data catalog.

Uses ``GET https://api.data.ferc.gov/v1/data-assets/`` with the key in
``Args.ferc_api_key`` (header ``X-Api-Key``).
"""

from __future__ import annotations

from typing import Any

from sourcing.FercApi import DEFAULT_TIMEOUT_SEC, ferc_api_key, ferc_get_json

DATA_ASSETS_URL = "https://api.data.ferc.gov/v1/data-assets/"


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
        self._api_key = api_key if api_key is not None else ferc_api_key()
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
        payload = ferc_get_json(
            DATA_ASSETS_URL,
            self._api_key,
            timeout_sec=self._timeout_sec,
        )
        return _assets_from_payload(payload)

    def close(self) -> None:
        """No persistent resources; provided for fetcher symmetry."""
        return


def _assets_from_payload(payload: Any) -> list[dict[str, Any]]:
    """Parse a data-assets body into a list of asset objects."""
    if not isinstance(payload, dict):
        raise RuntimeError("FERC catalog API returned an unexpected JSON type")
    assets = payload.get("data-assets")
    if not isinstance(assets, list):
        raise RuntimeError("FERC catalog API response has no data-assets list")
    return [asset for asset in assets if isinstance(asset, dict)]
