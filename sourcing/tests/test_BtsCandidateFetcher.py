"""Tests for BTS catalog URL helpers and candidate row building."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock

from sourcing.BtsCandidateFetcher import (
    BtsCandidateFetcher,
    collection_pid_from_catalog_url,
    is_dataset_doc,
    pid_to_view_url,
    record_id_from_source_url,
)
from utils.Args import Args


class TestBtsUrlHelpers(unittest.TestCase):
    """Tests for ROSA P URL and PID helpers."""

    def test_collection_pid_from_catalog_url(self) -> None:
        """Parse pid from a cbrowse catalog URL."""
        url = (
            "https://rosap.ntl.bts.gov/cbrowse"
            "?pid=dot%3A35533&parentId=dot%3A35533&sm_resource_type%5B%5D=Dataset"
        )
        self.assertEqual(collection_pid_from_catalog_url(url), "dot:35533")

    def test_pid_to_view_url(self) -> None:
        """Build canonical view URLs from Solr PIDs."""
        self.assertEqual(
            pid_to_view_url("dot:92758"),
            "https://rosap.ntl.bts.gov/view/dot/92758",
        )

    def test_record_id_from_source_url(self) -> None:
        """Extract numeric record ids from view URLs."""
        self.assertEqual(
            record_id_from_source_url("https://rosap.ntl.bts.gov/view/dot/92758"),
            "92758",
        )
        self.assertIsNone(record_id_from_source_url("https://example.com/"))

    def test_is_dataset_doc(self) -> None:
        """Detect Dataset resource types from Solr fields."""
        self.assertTrue(is_dataset_doc({"mods.sm_resource_type": ["Dataset"]}))
        self.assertTrue(is_dataset_doc({"dc.type": "Dataset"}))
        self.assertFalse(is_dataset_doc({"dc.type": ["Statistical Report"]}))


class TestBtsCandidateFetcher(unittest.TestCase):
    """Tests for candidate row construction."""

    def setUp(self) -> None:
        """Initialize Args defaults for fetcher construction."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "bts_candidate_fetcher"]
        Args.initialize()

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    def test_build_candidate_row_maps_metadata(self) -> None:
        """build_candidate_row maps Solr fields to a sourcing row."""
        fetcher = BtsCandidateFetcher(client=MagicMock())
        doc = {
            "PID": "dot:92758",
            "dc.title": ["Freight Analysis Framework (FAF) FAF6"],
            "dc.contributor.creator": [
                "United States. Department of Transportation. Bureau of Transportation Statistics"
            ],
            "dc.description.abstract": ["Summary text"],
            "mods.sm_resource_type": ["Dataset"],
            "DS1.filesize_tl": ["1048576"],
        }
        row = fetcher.build_candidate_row(doc)
        assert row is not None
        self.assertEqual(row["url"], "https://rosap.ntl.bts.gov/view/dot/92758")
        self.assertEqual(row["title"], "Freight Analysis Framework (FAF) FAF6")
        self.assertEqual(row["record_id"], "92758")
        self.assertEqual(row["agency"], "Bureau of Transportation Statistics")
        self.assertEqual(row["office"], "Department of Transportation")
        self.assertNotIn("summary", row)
        self.assertNotIn("num_files", row)
        self.assertNotIn("file_size", row)

    def test_build_candidate_row_skips_missing_title(self) -> None:
        """Missing title or PID returns None."""
        fetcher = BtsCandidateFetcher(client=MagicMock())
        self.assertIsNone(fetcher.build_candidate_row({"PID": "dot:1"}))


if __name__ == "__main__":
    unittest.main()
