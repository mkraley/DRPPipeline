"""Tests for Sheets read caching on InventorySheetUpdaterBase."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from publisher.GoogleSheetUpdater import GoogleSheetUpdater


class TestInventorySheetUpdaterCaches(unittest.TestCase):
    """Header and URL column caches avoid repeated Sheets reads."""

    def test_header_read_cached_across_column_mapping_calls(self) -> None:
        """Second column mapping uses cached header without another API get."""
        updater = GoogleSheetUpdater()
        mock_service = MagicMock()
        get_req = mock_service.spreadsheets.return_value.values.return_value.get.return_value
        get_req.execute.return_value = {
            "values": [["URL", "Title", "Claimed", "Data Added",
                        "Dataset Download Possible?", "Nominated to EOT / USGWDA"]]
        }

        required = [
            "URL",
            "Claimed",
            "Data Added",
            "Dataset Download Possible?",
            "Nominated to EOT / USGWDA",
        ]
        with patch(
            "publisher.inventory_sheet_updater_base.execute_sheets_request",
            side_effect=lambda req, **kwargs: req.execute(),
        ) as mock_exec:
            first = updater._get_column_mapping(
                mock_service, "sheet", "SSA", required, []
            )
            second = updater._get_column_mapping(
                mock_service, "sheet", "SSA", required, []
            )

        self.assertEqual(first, second)
        self.assertEqual(mock_exec.call_count, 1)

    def test_url_column_cached_for_find_and_append_row(self) -> None:
        """Find + next-append share one URL column read."""
        updater = GoogleSheetUpdater()
        mock_service = MagicMock()

        with patch(
            "publisher.inventory_sheet_updater_base.execute_sheets_request",
            return_value={"values": [["https://a.example"], ["https://b.example"]]},
        ) as mock_exec:
            row = updater._find_row_by_url(
                mock_service, "sheet", "SSA", "A", "https://missing.example"
            )
            append_row = updater._get_next_append_row(
                mock_service, "sheet", "SSA", "A"
            )

        self.assertIsNone(row)
        self.assertEqual(append_row, 4)
        self.assertEqual(mock_exec.call_count, 1)

    def test_remember_appended_url_extends_cache(self) -> None:
        """After append, cache grows so next append row advances."""
        updater = GoogleSheetUpdater()
        mock_service = MagicMock()

        with patch(
            "publisher.inventory_sheet_updater_base.execute_sheets_request",
            return_value={"values": [["https://a.example"]]},
        ):
            updater._get_url_column_values(mock_service, "sheet", "SSA", "A")

        updater._remember_appended_url(
            "sheet", "SSA", "A", "https://new.example"
        )
        self.assertEqual(
            updater._get_next_append_row(mock_service, "sheet", "SSA", "A"),
            4,
        )


if __name__ == "__main__":
    unittest.main()
