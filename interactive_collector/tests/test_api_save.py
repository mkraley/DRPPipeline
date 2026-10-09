"""Unit tests for interactive_collector.api_save."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils.Args import Args
from utils.Logger import Logger


class TestSaveMetadata(unittest.TestCase):
    """Tests for interactive collector save."""

    def setUp(self) -> None:
        """Initialize Args and an in-memory-style SQLite Storage."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "collect_interactively"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = Path(self.tmpdir) / "ic_save_test.db"
        Args._config["db_path"] = str(self.db_path)

        from storage import Storage

        Storage.reset()
        Storage.initialize("StorageSQLLite", db_path=self.db_path)
        self.drpid_collected = Storage.create_record("https://example.com/collected")

    def tearDown(self) -> None:
        from storage import Storage

        Storage.reset()
        sys.argv = self._original_argv

    def test_save_metadata_does_not_write_the_inventory_sheet(self) -> None:
        """Save updates the database and does not open the inventory sheet."""
        from interactive_collector.api_save import save_metadata

        with tempfile.TemporaryDirectory() as folder:
            with patch("publisher.inventory_sheet_updater.get_inventory_sheet_updater") as mock_sheet:
                save_metadata(
                    self.drpid_collected,
                    folder,
                    title="T",
                    summary="S",
                    keywords="k",
                    agency="A",
                    office="O",
                    time_start="2020",
                    time_end="2021",
                    download_date="2024-01-01",
                )
        mock_sheet.assert_not_called()

    def test_save_metadata_stores_geography_and_data_type(self) -> None:
        """Geography and data type are written only when the save includes them."""
        import sqlite3

        from interactive_collector.api_save import save_metadata

        save_metadata(
            self.drpid_collected,
            "",
            title="T",
            summary="S",
            keywords="",
            agency="A",
            office="",
            time_start="",
            time_end="",
            download_date="",
            geographic_coverage="United States",
            data_types="Observational data",
        )
        connection = sqlite3.connect(self.db_path)
        row = connection.execute(
            "SELECT geographic_coverage, data_types FROM projects WHERE DRPID = ?",
            (self.drpid_collected,),
        ).fetchone()
        connection.close()
        self.assertEqual(row, ("United States", "Observational data"))


if __name__ == "__main__":
    unittest.main()
