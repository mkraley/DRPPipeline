"""Tests for GlobusPathInventory."""

from __future__ import annotations

import sys
import unittest
from typing import Any

from utils.Args import Args
from utils.Logger import Logger

from collectors.GlobusPathInventory import GlobusPathInventory


class TestGlobusPathInventory(unittest.TestCase):
    """Tests for recursive Globus directory inventory."""

    def setUp(self) -> None:
        """Initialize Args and Logger for each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "adc_globus_survey"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    def test_summarize_nested_tree(self) -> None:
        """File sizes and counts include nested directories."""
        listings: dict[str, list[dict[str, Any]]] = {
            "/node29313/": [
                {"name": "a.csv", "type": "file", "size": 100},
                {"name": "subdir", "type": "dir"},
            ],
            "/node29313/subdir/": [
                {"name": "b.csv", "type": "file", "size": 250},
            ],
        }

        def list_entries(endpoint_id: str, path: str) -> list[dict[str, Any]]:
            self.assertEqual(endpoint_id, "src-ep")
            return listings[path]

        summary = GlobusPathInventory(list_entries).summarize("src-ep", "/node29313")
        self.assertEqual(summary.file_count, 2)
        self.assertEqual(summary.dir_count, 1)
        self.assertEqual(summary.total_bytes, 350)
        self.assertEqual(summary.root_path, "/node29313/")


if __name__ == "__main__":
    unittest.main()
