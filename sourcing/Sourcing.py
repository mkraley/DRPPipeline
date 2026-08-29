"""
Sourcing entry point for DRP Pipeline.

Delegates to the implementation selected by ``Args.source`` (see
:class:`SourcingFactory`).
"""

from __future__ import annotations

from sourcing.SourcingFactory import create_sourcing
from sourcing.SpreadsheetSourcing import SpreadsheetSourcing


class Sourcing:
    """
    Router invoked by the orchestrator as module ``sourcing``.

    Selects :class:`SpreadsheetSourcing`, :class:`AdcSourcing`, or future
    source-specific implementations based on ``Args.source``.
    """

    def run(self, drpid: int) -> None:
        """
        Run sourcing for the configured source.

        Args:
            drpid: Use -1 (orchestrator convention for batch sourcing).
        """
        create_sourcing().run(drpid)

    def get_candidate_urls(
        self, limit: int | None = None
    ) -> tuple[list[dict[str, str]], int]:
        """
        Preview spreadsheet candidate URLs.

        Always uses :class:`SpreadsheetSourcing` regardless of ``Args.source``,
        since ADC preview uses the Figshare API path instead.

        Args:
            limit: Max rows to return; None means unlimited.

        Returns:
            Tuple of candidate row dicts and skipped row count.
        """
        return SpreadsheetSourcing().get_candidate_urls(limit=limit)
