"""Tests for scripts.retry_publisher_sheet DRPID resolution."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from scripts.retry_publisher_sheet import published_drpids, resolve_drpids


class TestRetryPublisherSheetIds(unittest.TestCase):
    """Unit tests for DRPID CLI resolution helpers."""

    def test_resolve_drpids_empty(self) -> None:
        """Empty tokens mean caller should fall back to all published."""
        self.assertEqual(resolve_drpids([]), [])

    def test_resolve_drpids_range(self) -> None:
        """Inclusive ranges expand to individual IDs."""
        self.assertEqual(resolve_drpids(["100-103"]), [100, 101, 102, 103])

    def test_resolve_drpids_space_separated(self) -> None:
        """Space-separated IDs are joined then parsed."""
        self.assertEqual(resolve_drpids(["101", "102", "103"]), [101, 102, 103])

    def test_resolve_drpids_comma_and_range_mix(self) -> None:
        """Comma lists and ranges work together."""
        self.assertEqual(resolve_drpids(["5,7,10-12"]), [5, 7, 10, 11, 12])

    def test_resolve_drpids_invalid_raises(self) -> None:
        """Invalid tokens raise ValueError."""
        with self.assertRaises(ValueError):
            resolve_drpids(["abc"])

    def test_published_drpids_excludes_errored(self) -> None:
        """Default listing omits published rows that still have errors."""
        mock_instance = MagicMock()
        mock_instance.list_eligible_projects.return_value = [
            {"DRPID": 2},
            {"DRPID": 5},
        ]
        with patch("storage.Storage.Storage._initialized", True), patch(
            "storage.Storage.Storage._instance", mock_instance
        ):
            self.assertEqual(published_drpids(), [2, 5])
        mock_instance.list_eligible_projects.assert_called_once_with(
            "published", None
        )


if __name__ == "__main__":
    unittest.main()
