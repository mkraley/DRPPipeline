"""
HTTP client for Social Security Administration datasets in the Data.gov catalog.

Thin wrapper around ``DataGovCatalogClient`` with org slug ``ssa``.
"""

from __future__ import annotations

from sourcing.DataGovCatalogClient import (
    DEFAULT_PER_PAGE,
    DEFAULT_TIMEOUT_SEC,
    GSA_SEARCH_URL,
    DataGovCatalogClient,
)

DEFAULT_ORG_SLUG = "ssa"

__all__ = [
    "DEFAULT_ORG_SLUG",
    "DEFAULT_PER_PAGE",
    "DEFAULT_TIMEOUT_SEC",
    "GSA_SEARCH_URL",
    "SsaCatalogClient",
]


class SsaCatalogClient(DataGovCatalogClient):
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
        Initialize the SSA catalog client.

        Args:
            api_key: api.data.gov key; defaults to ``Args.gsa_api_key``.
            org_slug: Organization slug; defaults to ``ssa``.
            per_page: Results per search page.
            timeout_sec: HTTP timeout per request.
        """
        super().__init__(
            org_slug=org_slug or DEFAULT_ORG_SLUG,
            api_key=api_key,
            per_page=per_page,
            timeout_sec=timeout_sec,
        )
