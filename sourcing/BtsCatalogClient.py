"""
Playwright client for ROSA P collection JSON export.

The BTS site blocks plain HTTP clients; Chromium navigation returns Solr JSON
from ``/fedora/export/view/collection/{pid}``.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from collectors.PlaywrightSession import PlaywrightSession
from utils.Logger import Logger

DEFAULT_PAGE_SIZE = 200
EXPORT_PATH = "/fedora/export/view/collection/"


class BtsCatalogClient:
    """Fetch paginated collection metadata from the ROSA P JSON export API."""

    def __init__(
        self,
        *,
        session: PlaywrightSession | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        base_url: str = "https://rosap.ntl.bts.gov",
    ) -> None:
        """
        Initialize the catalog client.

        Args:
            session: Optional Playwright session (created when omitted).
            page_size: Solr ``rows`` parameter per request.
            base_url: ROSA P site origin.
        """
        self._session = session
        self._owns_session = session is None
        self._page_size = page_size
        self._base_url = base_url.rstrip("/")

    def fetch_collection_page(
        self,
        collection_pid: str,
        *,
        start: int = 0,
        rows: int | None = None,
    ) -> dict[str, Any]:
        """
        Fetch one Solr JSON page for a collection PID.

        Args:
            collection_pid: Collection identifier (e.g. ``dot:35533``).
            start: Zero-based offset into the collection.
            rows: Page size override; defaults to ``page_size``.

        Returns:
            Parsed Solr response document.

        Raises:
            RuntimeError: When Playwright fails or the response is not JSON.
            ValueError: When Solr returns a non-zero status.
        """
        page_rows = rows if rows is not None else self._page_size
        encoded_pid = quote(collection_pid, safe=":")
        url = (
            f"{self._base_url}{EXPORT_PATH}{encoded_pid}"
            f"?rows={page_rows}&start={start}"
        )
        self._ensure_session()
        assert self._session is not None
        if not self._session.goto(url, wait_until="domcontentloaded", timeout=120_000):
            raise RuntimeError(f"Failed to load BTS catalog page: {url}")

        page = self._session.page
        if page is None:
            raise RuntimeError("Playwright page is not available")

        try:
            raw_text = page.locator("pre").inner_text(timeout=30_000)
        except Exception as exc:
            raise RuntimeError(f"BTS catalog response missing JSON body: {url}") from exc

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"BTS catalog response is not valid JSON: {url}") from exc

        header = payload.get("responseHeader", {})
        status = header.get("status")
        if status not in (0, "0", None):
            raise ValueError(
                f"BTS catalog Solr error status={status!r} for collection {collection_pid}"
            )
        if "response" not in payload:
            raise RuntimeError(f"BTS catalog response missing 'response' key: {url}")
        return payload

    def close(self) -> None:
        """Close the Playwright session when this client owns it."""
        if self._owns_session and self._session is not None:
            self._session.close()
            self._session = None

    def _ensure_session(self) -> None:
        """Start Playwright when no session was injected."""
        if self._session is not None:
            return
        self._session = PlaywrightSession(headless=True)
        if not self._session.start(create_page=True):
            self._session = None
            raise RuntimeError("Failed to start Playwright for BTS catalog access")
