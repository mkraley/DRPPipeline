"""
EPA collector for DRP Pipeline.

Thin wrapper around ``DataGovCollector`` for catalog.data.gov EPA datasets.
Run via orchestrator when ``Args.source`` is ``epa``.
"""

from __future__ import annotations

from collectors.DataGovCollector import DataGovCollector
from sourcing.EpaSourcing import AGENCY, OFFICE

_EPA_WARMUP_URL = "https://www.epa.gov/"


class EpaCollector(DataGovCollector):
    """Collect EPA catalog metadata and dataset files."""

    def __init__(self, headless: bool = True) -> None:
        """
        Initialize the EPA collector.

        Args:
            headless: Launch Playwright headless when True.
        """
        super().__init__(
            source_label="EPA",
            agency=AGENCY,
            office=OFFICE,
            warmup_url=_EPA_WARMUP_URL,
            headless=headless,
        )
