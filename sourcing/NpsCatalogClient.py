"""
HTTP client for NPS IRMA DataStore collection and profile APIs.
"""

from __future__ import annotations

from typing import Any

import requests

from utils.Args import Args
from utils.url_utils import requests_verify

PROFILE_URL = "https://irmaservices.nps.gov/datastore/v8/rest/Profile/{}"
COLLECTION_GET_URL = "https://irma.nps.gov/DataStore/Collection/GetById/{}"
COLLECTION_REFS_URL = (
    "https://irma.nps.gov/DataStore/Collection/GetCollectionReferencesForProfile"
)
DEFAULT_TIMEOUT_SEC = 45
_JSON_HEADERS = {
    "User-Agent": "Mozilla/5.0 DRPPipeline-NPS",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}


class NpsCatalogClient:
    """Fetch IRMA Collection metadata, Program members, and reference Profiles."""

    def __init__(self, *, timeout_sec: int | None = None) -> None:
        """
        Initialize the IRMA client.

        Args:
            timeout_sec: HTTP timeout; defaults to ``nps_request_timeout``.
        """
        default_timeout = int(getattr(Args, "nps_request_timeout", DEFAULT_TIMEOUT_SEC) or DEFAULT_TIMEOUT_SEC)
        self._timeout_sec = timeout_sec if timeout_sec is not None else default_timeout

    def fetch_profile(self, reference_id: int) -> dict[str, Any]:
        """
        Return a v8 Profile JSON object for one IRMA reference.

        Args:
            reference_id: IRMA reference id (Program, Project, or Product).
        """
        payload = self._get_json(PROFILE_URL.format(int(reference_id)))
        if not isinstance(payload, dict):
            raise RuntimeError(f"IRMA Profile {reference_id} returned a non-object")
        return payload

    def fetch_collection(self, collection_id: int) -> dict[str, Any]:
        """
        Return Collection GetById metadata.

        Args:
            collection_id: IRMA Collection id (not a reference id).
        """
        payload = self._get_json(COLLECTION_GET_URL.format(int(collection_id)))
        if not isinstance(payload, dict):
            raise RuntimeError(f"IRMA Collection {collection_id} returned a non-object")
        return payload

    def fetch_collection_programs(self, collection_id: int) -> list[dict[str, Any]]:
        """
        Return Program references that belong to a Collection.

        Args:
            collection_id: IRMA Collection id.
        """
        payload = self._post_form(COLLECTION_REFS_URL, {"collectionId": int(collection_id)})
        if not isinstance(payload, list):
            raise RuntimeError(
                f"IRMA Collection {collection_id} program list returned a non-list"
            )
        return [row for row in payload if isinstance(row, dict)]

    def close(self) -> None:
        """No persistent resources; provided for fetcher symmetry."""
        return

    def _get_json(self, url: str) -> Any:
        """GET a JSON payload from IRMA."""
        try:
            response = requests.get(
                url,
                headers=_JSON_HEADERS,
                timeout=self._timeout_sec,
                verify=requests_verify(),
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"IRMA GET failed for {url}: {exc}") from exc
        return self._parse_json_response(response, url)

    def _post_form(self, url: str, data: dict[str, Any]) -> Any:
        """POST form fields and return JSON."""
        try:
            response = requests.post(
                url,
                headers={
                    **_JSON_HEADERS,
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                },
                data=data,
                timeout=self._timeout_sec,
                verify=requests_verify(),
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"IRMA POST failed for {url}: {exc}") from exc
        return self._parse_json_response(response, url)

    @staticmethod
    def _parse_json_response(response: requests.Response, url: str) -> Any:
        """Raise on HTTP errors and parse JSON."""
        if response.status_code >= 400:
            raise RuntimeError(f"IRMA HTTP {response.status_code} for {url}: {response.text[:300]}")
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(f"IRMA returned non-JSON for {url}") from exc
