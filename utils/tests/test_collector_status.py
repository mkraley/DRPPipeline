"""Tests for collector status merge helpers."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from utils.collector_status import (
    MAX_DOWNLOAD_BYTES,
    STATUS_COLLECTED,
    STATUS_COLLECTED_EXTERNAL_ARCHIVE,
    STATUS_COLLECTED_LARGE_FILE,
    deferred_download_skip_note,
    download_budget_exhausted,
    large_file_skip_note,
    merge_result_to_storage,
    resolve_inventory_collected_status,
    resolve_standard_collected_status,
    would_exceed_download_budget,
)


class TestCollectorStatus(unittest.TestCase):
    """Tests for shared collector status helpers."""

    def test_large_file_skip_note_includes_size_and_url(self) -> None:
        """Skip note mentions filename, size label, and manual URL."""
        note = large_file_skip_note("big.zip", "https://example.com/big.zip", 2 * 1024**3)
        self.assertIn("big.zip", note)
        self.assertIn("Skipped download (>1GB)", note)
        self.assertIn("https://example.com/big.zip", note)

    def test_deferred_download_skip_note_without_size(self) -> None:
        """Deferred notes omit the size parenthetical when unknown."""
        note = deferred_download_skip_note("readme.txt", "https://example.com/readme.txt")
        self.assertIn("readme.txt", note)
        self.assertNotIn("readme.txt (", note)

    def test_would_exceed_download_budget(self) -> None:
        """Cumulative budget blocks downloads that would exceed 1 GB."""
        half = MAX_DOWNLOAD_BYTES // 2
        self.assertFalse(would_exceed_download_budget(half, half))
        self.assertTrue(would_exceed_download_budget(half, half + 1))
        self.assertTrue(would_exceed_download_budget(MAX_DOWNLOAD_BYTES, 1))
        self.assertFalse(would_exceed_download_budget(half, None))

    def test_download_budget_exhausted(self) -> None:
        """Budget is exhausted at exactly 1 GB."""
        self.assertFalse(download_budget_exhausted(MAX_DOWNLOAD_BYTES - 1))
        self.assertTrue(download_budget_exhausted(MAX_DOWNLOAD_BYTES))

    def test_resolve_inventory_large_file_status(self) -> None:
        """Inventory mode sets collected - large file when flagged."""
        result = {"folder_path": "C:\\Data\\1", "_skipped_large_file": True}
        resolve_inventory_collected_status(result, has_errors=False)
        self.assertEqual(result["status"], STATUS_COLLECTED_LARGE_FILE)
        self.assertNotIn("_skipped_large_file", result)

    def test_resolve_inventory_external_archive_status(self) -> None:
        """Inventory mode sets collected - external archive when flagged."""
        result = {"folder_path": "C:\\Data\\1", "_external_archive": True}
        resolve_inventory_collected_status(result, has_errors=False)
        self.assertEqual(result["status"], STATUS_COLLECTED_EXTERNAL_ARCHIVE)

    def test_resolve_inventory_skips_status_when_errors(self) -> None:
        """Inventory mode does not set status when errors exist."""
        result = {"folder_path": "C:\\Data\\1", "status": "pending"}
        resolve_inventory_collected_status(result, has_errors=True)
        self.assertNotIn("status", result)

    def test_resolve_standard_collected_status(self) -> None:
        """Standard mode defaults to collected when folder_path is present."""
        result = {"folder_path": "C:\\Data\\1"}
        resolve_standard_collected_status(result, previous_status="sourced")
        self.assertEqual(result["status"], STATUS_COLLECTED)

    @patch("utils.collector_status.Storage")
    def test_merge_result_to_storage_inventory(self, mock_storage: MagicMock) -> None:
        """merge_result_to_storage applies inventory status resolution."""
        mock_storage.get.return_value = {"errors": ""}
        merge_result_to_storage(
            1,
            {"folder_path": "C:\\Data\\1", "_skipped_large_file": True},
            status_mode="inventory",
        )
        fields = mock_storage.update_record.call_args[0][1]
        self.assertEqual(fields["status"], STATUS_COLLECTED_LARGE_FILE)

    @patch("utils.collector_status.Storage")
    def test_merge_result_to_storage_notes_only(self, mock_storage: MagicMock) -> None:
        """notes_only mode merges fields without setting status."""
        merge_result_to_storage(
            1,
            {"status_notes": "line one"},
            status_mode="notes_only",
        )
        fields = mock_storage.update_record.call_args[0][1]
        self.assertEqual(fields["status_notes"], "line one")
        self.assertNotIn("status", fields)


if __name__ == "__main__":
    unittest.main()
