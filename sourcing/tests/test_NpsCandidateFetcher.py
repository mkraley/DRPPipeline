"""Tests for NPS IRMA candidate enumeration."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock

from sourcing.NpsCandidateFetcher import NpsCandidateFetcher
from utils.Args import Args

COLLECTION = {"Id": 9688, "Title": "IMD Programs"}
PROGRAM_ROW = {"Id": 2310251, "Title": "APHN"}
PROGRAM_PROFILE = {
    "referenceId": 2310251,
    "bibliography": {"title": "APHN"},
    "children": [
        {"referenceId": 1001, "referenceType": "Project"},
        {"referenceId": 1002, "referenceType": "Project"},
        {"referenceId": 1001, "referenceType": "Project"},
    ],
}
PUBLIC_PROJECT = {
    "referenceId": 1001,
    "visibility": "Public",
    "bibliography": {"title": "Keep Me"},
    "filesAndLinks": [],
    "products": [
        {
            "referenceId": 2001,
            "title": "Public Package",
            "referenceType": "Data Package",
            "fileCount": 3,
            "fileAccess": "Public",
            "visibility": "Public",
        }
    ],
}
RESTRICTED_PROJECT = {
    "referenceId": 1002,
    "visibility": "Public",
    "bibliography": {"title": "Skip Me"},
    "filesAndLinks": [],
    "products": [
        {
            "referenceId": 2002,
            "title": "Restricted Package",
            "referenceType": "Data Package",
            "fileCount": 4,
            "fileAccess": "Restricted",
            "visibility": "Public",
        }
    ],
}


def _client() -> MagicMock:
    """Return a catalog client with APHN-sized fixtures."""
    client = MagicMock()
    client.fetch_collection.return_value = COLLECTION
    client.fetch_collection_programs.return_value = [PROGRAM_ROW]
    client.fetch_profile.side_effect = lambda rid: {
        2310251: PROGRAM_PROFILE,
        1001: PUBLIC_PROJECT,
        1002: RESTRICTED_PROJECT,
    }[rid]
    return client


class TestNpsCandidateFetcher(unittest.TestCase):
    """Tests for Collection → Program → Project walking."""

    def setUp(self) -> None:
        """Initialize Args for fetcher defaults."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "nps_candidate_fetcher"]
        Args.initialize()

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    def test_list_project_rows_keeps_public_files_only(self) -> None:
        """Duplicate children collapse; restricted products are skipped."""
        rows = NpsCandidateFetcher(
            client=_client(),
            request_delay=0,
            collection_id=9688,
            program_id=2310251,
        ).list_project_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["irma_project_id"], 1001)
        self.assertEqual(rows[0]["public_file_count"], 3)
        self.assertEqual(rows[0]["products"][0]["irma_product_id"], 2001)

    def test_missing_program_raises(self) -> None:
        """A configured Program that is not in the Collection is an error."""
        client = _client()
        with self.assertRaises(ValueError):
            NpsCandidateFetcher(
                client=client,
                request_delay=0,
                collection_id=9688,
                program_id=999,
            ).list_project_rows()


if __name__ == "__main__":
    unittest.main()
