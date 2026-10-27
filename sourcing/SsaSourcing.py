"""
Social Security Administration sourcing module for DRP Pipeline.

Thin wrapper around ``DataGovSourcing`` for the Data.gov ``ssa`` organization.
Run via orchestrator when ``Args.source`` is ``ssa``::

    python main.py source
"""

from __future__ import annotations

from sourcing.DataGovSourcing import DataGovSourcing
from sourcing.SsaCandidateFetcher import SsaCandidateFetcher


class SsaSourcing(DataGovSourcing):
    """
    Source SSA datasets into Storage from the Data.gov catalog.

    Already-sourced catalog slugs are skipped before insert.
    """

    def __init__(
        self,
        *,
        fetcher: SsaCandidateFetcher | None = None,
    ) -> None:
        """
        Initialize the SSA sourcing module.

        Args:
            fetcher: Candidate fetcher (created when omitted).
        """
        super().__init__(
            fetcher=fetcher or SsaCandidateFetcher(),
            source_label="SSA",
        )
