"""Tests for SSA thin wrapper around DataGovCandidateFetcher."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock

from sourcing.SsaCandidateFetcher import AGENCY, SsaCandidateFetcher
from utils.Args import Args


def _result() -> dict:
    """Build a minimal collectible SSA search result."""
    return {
        "slug": "baby-names",
        "title": "Baby Names",
        "identifier": "US-GOV-SSA-338",
        "dcat": {
            "accessLevel": "public",
            "identifier": "US-GOV-SSA-338",
            "distribution": [
                {
                    "format": "ZIP",
                    "downloadURL": "https://www.ssa.gov/oact/babynames/names.zip",
                }
            ],
        },
    }


class TestSsaCandidateFetcher(unittest.TestCase):
    """Tests for SSA agency labeling on shared fetcher."""

    def setUp(self) -> None:
        """Initialize Args defaults for fetcher construction."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "ssa_candidate_fetcher"]
        Args.initialize()

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    def test_build_candidate_row_uses_ssa_agency(self) -> None:
        """SSA wrapper stamps Social Security Administration labels."""
        fetcher = SsaCandidateFetcher(client=MagicMock(), request_delay=0)
        row = fetcher.build_candidate_row(_result())
        assert row is not None
        self.assertEqual(row["agency"], AGENCY)
        self.assertEqual(row["url"], "https://catalog.data.gov/dataset/baby-names")


if __name__ == "__main__":
    unittest.main()
