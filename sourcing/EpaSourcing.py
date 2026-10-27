"""
EPA sourcing module for DRP Pipeline.

Sources public file datasets from the Data.gov ``epa`` organization via the
shared Data.gov catalog stack. Run via orchestrator when ``Args.source`` is
``epa``::

    python main.py source --source epa
"""

from __future__ import annotations

from sourcing.DataGovCandidateFetcher import DataGovCandidateFetcher
from sourcing.DataGovCatalogClient import DataGovCatalogClient
from sourcing.DataGovSourcing import DataGovSourcing
from utils.Args import Args

AGENCY = "U.S. Environmental Protection Agency"
OFFICE = "U.S. Environmental Protection Agency"
DEFAULT_ORG_SLUG = "epa"


class EpaSourcing(DataGovSourcing):
    """
    Source EPA datasets into Storage from the Data.gov catalog.

    Already-sourced catalog slugs are skipped before insert.
    """

    def __init__(
        self,
        *,
        fetcher: DataGovCandidateFetcher | None = None,
    ) -> None:
        """
        Initialize the EPA sourcing module.

        Args:
            fetcher: Candidate fetcher (created when omitted).
        """
        super().__init__(
            fetcher=fetcher or _default_epa_fetcher(),
            source_label="EPA",
        )


def _default_epa_fetcher() -> DataGovCandidateFetcher:
    """Build a Data.gov fetcher for the EPA organization slug."""
    org_slug = str(getattr(Args, "org_slug", None) or DEFAULT_ORG_SLUG).strip()
    if not org_slug:
        org_slug = DEFAULT_ORG_SLUG
    return DataGovCandidateFetcher(
        agency=AGENCY,
        office=OFFICE,
        client=DataGovCatalogClient(org_slug=org_slug),
        source_label="EPA",
    )
