"""Fetch one FERC dataset's details, dictionary, and data pages."""

from __future__ import annotations

from typing import Any

from sourcing.FercApi import API_ROOT, DEFAULT_TIMEOUT_SEC, FercNotFound, ferc_api_key, ferc_get_json

DATA_PAGE_SIZE = 10000


class FercDatasetClient:
    """Read dataset resources from ``https://api.data.ferc.gov``."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    ) -> None:
        """
        Initialize the client.

        Args:
            api_key: FERC API key; defaults to ``Args.ferc_api_key``.
            timeout_sec: HTTP timeout per request.
        """
        self._api_key = api_key if api_key is not None else ferc_api_key()
        self._timeout_sec = timeout_sec

    def fetch_details(self, dataset_id: int) -> dict[str, Any] | None:
        """
        Return the details object, or None when the API has no details.

        Args:
            dataset_id: FERC dataset id.

        Returns:
            Parsed details JSON.
        """
        payload = self._get_or_missing(f"/v1/dataset/{dataset_id}/details/")
        if payload is None:
            return None
        if not isinstance(payload, dict):
            raise RuntimeError(f"FERC details for dataset {dataset_id} was not an object")
        return payload

    def fetch_dictionary(self, dataset_id: int) -> list[dict[str, Any]] | None:
        """
        Return API dictionary rows, or None when the dataset has none.

        Args:
            dataset_id: FERC dataset id.

        Returns:
            Dictionary rows from the short API form.
        """
        payload = self._get_or_missing(f"/v1/dataset/{dataset_id}/dictionary/")
        if payload is None:
            return None
        if not isinstance(payload, list):
            raise RuntimeError(f"FERC dictionary for dataset {dataset_id} was not a list")
        return [row for row in payload if isinstance(row, dict)]

    def fetch_data_page(self, dataset_id: int, *, offset: int, limit: int) -> dict[str, Any]:
        """
        Return one page of dataset rows.

        Args:
            dataset_id: FERC dataset id.
            offset: Zero-based row offset.
            limit: Page size. The API accepts up to 10,000.

        Returns:
            ``row_data`` and ``has_more``.
        """
        payload = ferc_get_json(
            f"{API_ROOT}/v1/dataset/{dataset_id}/data/?limit={limit}&offset={offset}",
            self._api_key,
            timeout_sec=self._timeout_sec,
        )
        if not isinstance(payload, dict):
            raise RuntimeError(f"FERC data for dataset {dataset_id} was not an object")
        rows = payload.get("row_data")
        if not isinstance(rows, list):
            raise RuntimeError(f"FERC data for dataset {dataset_id} has no row_data list")
        return {
            "row_data": [row for row in rows if isinstance(row, dict)],
            "has_more": bool(payload.get("has_more")),
        }

    def _get_or_missing(self, path: str) -> Any | None:
        """GET ``path`` and map HTTP 404 to None."""
        try:
            return ferc_get_json(
                f"{API_ROOT}{path}",
                self._api_key,
                timeout_sec=self._timeout_sec,
            )
        except FercNotFound:
            return None
