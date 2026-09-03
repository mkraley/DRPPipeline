"""
Enumerate BTS dataset candidates from the ROSA P BTS Products collection.

Reads collection metadata via :class:`BtsCatalogClient`, filters to Dataset
resource types, and builds sourcing candidate rows.
"""

from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from sourcing.BtsCatalogClient import BtsCatalogClient
from utils.Args import Args
from utils.Logger import Logger

AGENCY = "Department of Transportation"
OFFICE = "Bureau of Transportation Statistics"
VIEW_URL_RE = re.compile(r"/view/dot/(\d+)/?$")
DEFAULT_CATALOG_URL = (
    "https://rosap.ntl.bts.gov/cbrowse"
    "?pid=dot%3A35533&parentId=dot%3A35533&sm_resource_type%5B%5D=Dataset"
)


def collection_pid_from_catalog_url(catalog_url: str) -> str:
    """
    Parse a ROSA P cbrowse URL and return the collection PID.

    Args:
        catalog_url: Catalog browse URL containing ``pid`` or ``parentId``.

    Returns:
        Decoded PID such as ``dot:35533``.

    Raises:
        ValueError: When no PID parameter is present.
    """
    query = parse_qs(urlparse(catalog_url).query)
    for key in ("pid", "parentId"):
        values = query.get(key)
        if values and values[0].strip():
            return unquote(values[0].strip())
    raise ValueError(f"No collection pid found in catalog URL: {catalog_url}")


def record_id_from_source_url(source_url: str) -> str | None:
    """
    Extract the numeric ROSA P record id from a view URL.

    Args:
        source_url: Portal URL (``.../view/dot/92758``).

    Returns:
        Record id string or None when the URL does not match.
    """
    match = VIEW_URL_RE.search(source_url.strip())
    return match.group(1) if match else None


def pid_to_view_url(pid: str, *, base_url: str = "https://rosap.ntl.bts.gov") -> str:
    """
    Build the public view URL for a ROSA P PID.

    Args:
        pid: Record PID such as ``dot:92758``.
        base_url: Site origin.

    Returns:
        Canonical view URL.
    """
    numeric_id = pid.split(":", 1)[-1]
    return f"{base_url.rstrip('/')}/view/dot/{numeric_id}"


def is_dataset_doc(doc: dict[str, Any]) -> bool:
    """
    Return True when a Solr document represents a Dataset resource.

    Args:
        doc: Solr document from the collection export.

    Returns:
        True when ``dc.type`` or ``mods.sm_resource_type`` includes Dataset.
    """
    for key in ("mods.sm_resource_type", "dc.type"):
        values = doc.get(key) or []
        if isinstance(values, str):
            values = [values]
        if any(str(value).strip().lower() == "dataset" for value in values):
            return True
    return False


class BtsCandidateFetcher:
    """List dataset candidates and build storage-ready rows."""

    def __init__(
        self,
        *,
        client: BtsCatalogClient | None = None,
        request_delay: float | None = None,
    ) -> None:
        """
        Initialize the fetcher.

        Args:
            client: Catalog client (created when omitted).
            request_delay: Seconds between catalog page requests; defaults to
                ``bts_request_delay`` from Args or 0.1.
        """
        self._client = client or BtsCatalogClient()
        default_delay = float(getattr(Args, "bts_request_delay", 0.1) or 0.1)
        self._request_delay = request_delay if request_delay is not None else default_delay

    def list_dataset_rows(self, collection_pid: str | None = None) -> list[dict[str, str]]:
        """
        Return all Dataset rows for the configured BTS collection.

        Args:
            collection_pid: Override collection PID; defaults from Args.

        Returns:
            Candidate rows with url, title, agency, office, and record_id.
        """
        pid = collection_pid or self._collection_pid()
        rows: list[dict[str, str]] = []
        start = 0
        total = None

        while total is None or start < total:
            payload = self._client.fetch_collection_page(pid, start=start)
            response = payload["response"]
            total = int(response.get("numFound", 0))
            docs = response.get("docs") or []
            if not docs:
                break

            for doc in docs:
                if not is_dataset_doc(doc):
                    continue
                row = self.build_candidate_row(doc)
                if row is not None:
                    rows.append(row)

            start += len(docs)
            Logger.debug(
                "BTS catalog page fetched: start=%s total=%s datasets=%s",
                start,
                total,
                len(rows),
            )
            if self._request_delay > 0 and start < total:
                time.sleep(self._request_delay)

        return rows

    def build_candidate_row(self, doc: dict[str, Any]) -> dict[str, str] | None:
        """
        Convert a Solr document to a sourcing candidate row.

        Args:
            doc: Solr document from the collection export.

        Returns:
            Candidate dict or None when PID/title is missing.
        """
        pid = str(doc.get("PID") or "").strip()
        title = _first_text(doc.get("dc.title")) or _first_text(doc.get("mods.title"))
        if not pid or not title:
            return None

        return {
            "url": pid_to_view_url(pid),
            "title": title,
            "agency": AGENCY,
            "office": OFFICE,
            "record_id": pid.split(":", 1)[-1],
        }

    def close(self) -> None:
        """Release the underlying catalog client."""
        self._client.close()

    def _collection_pid(self) -> str:
        """Resolve collection PID from Args."""
        catalog_url = str(getattr(Args, "bts_catalog_url", None) or DEFAULT_CATALOG_URL)
        return collection_pid_from_catalog_url(catalog_url)


def _first_text(value: Any) -> str:
    """Return the first non-empty string from a Solr field value."""
    if value is None:
        return ""
    if isinstance(value, list):
        for item in value:
            text = str(item or "").strip()
            if text:
                return text
        return ""
    return str(value).strip()
