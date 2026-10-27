"""
Social Security Administration collector for DRP Pipeline.

Thin wrapper around ``DataGovCollector`` for catalog.data.gov SSA datasets.
Akamai blocks plain HTTP on ssa.gov, so a warmup visit seeds cookies.
"""

from __future__ import annotations

from collectors.DataGovCollector import DataGovCollector
from sourcing.SsaCandidateFetcher import AGENCY, OFFICE

_SSA_WARMUP_URL = "https://www.ssa.gov/data/"


class SsaCollector(DataGovCollector):
    """Collect SSA catalog metadata and dataset files."""

    def __init__(self, headless: bool = True) -> None:
        """
        Initialize the SSA collector.

        Args:
            headless: Launch Playwright headless when True.
        """
        super().__init__(
            source_label="SSA",
            agency=AGENCY,
            office=OFFICE,
            warmup_url=_SSA_WARMUP_URL,
            headless=headless,
        )
