"""Tests for NPS Data Table Info CSV sidecars."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from collectors.NpsDataTableSidecar import write_data_table_csv, write_sidecars_for_files
from collectors.NpsDownloadPlan import NpsPlannedFile


class TestNpsDataTableSidecar(unittest.TestCase):
    """Tests for LoadDataTable sidecar writing."""

    def test_write_data_table_csv_utf8_sig(self) -> None:
        """Sidecars use UTF-8-sig and include column metadata."""
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "HUC_data_table_info.csv"
            write_data_table_csv(
                dest,
                [
                    {
                        "ColumnName": "code",
                        "Definition": "hydrologic unit code",
                        "Storage": "string",
                        "Unit": None,
                        "DataTableScales": [],
                    }
                ],
            )
            raw = dest.read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
            text = dest.read_text(encoding="utf-8-sig")
            self.assertIn("column_name", text)
            self.assertIn("hydrologic unit code", text)

    def test_write_sidecars_skips_zero_table_count(self) -> None:
        """Holdings without DataTableCount do not fetch LoadDataTable."""
        client = MagicMock()
        files = [
            NpsPlannedFile(
                url="https://irma.nps.gov/DataStore/DownloadFile/1",
                filename="readme.xml",
                relative_dir="pkg",
                resource_id=1,
                data_table_count=0,
                reference_id=9,
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            notes = write_sidecars_for_files(1, Path(tmp), files, client)
        self.assertEqual(notes, [])
        client.fetch_data_table.assert_not_called()

    def test_write_sidecars_fetches_table_info(self) -> None:
        """Holdings with DataTableCount write a sidecar CSV."""
        client = MagicMock()
        client.fetch_data_table.return_value = [
            {"ColumnName": "code", "Definition": "id", "Storage": "string"}
        ]
        files = [
            NpsPlannedFile(
                url="https://irma.nps.gov/DataStore/DownloadFile/716591",
                filename="HUC.csv",
                relative_dir="pkg",
                resource_id=716591,
                data_table_count=2,
                reference_id=2308545,
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            notes = write_sidecars_for_files(1, folder, files, client)
            sidecar = folder / "pkg" / "HUC_data_table_info.csv"
            self.assertTrue(sidecar.is_file())
            folder_csv = folder / "pkg" / "data_table_info.csv"
            self.assertTrue(folder_csv.is_file())
            text = folder_csv.read_text(encoding="utf-8-sig")
            self.assertIn("source_file", text)
            self.assertIn("HUC.csv", text)
        self.assertEqual(notes, [])
        client.fetch_data_table.assert_called_once_with(2308545, 716591)

    def test_write_sidecars_at_project_and_product_folders(self) -> None:
        """Data Table Info is written in both _project_files and product folders."""
        client = MagicMock()
        client.fetch_data_table.return_value = [
            {"ColumnName": "code", "Definition": "id", "Storage": "string"}
        ]
        files = [
            NpsPlannedFile(
                url="https://irma.nps.gov/DataStore/DownloadFile/1",
                filename="project.csv",
                relative_dir="_project_files",
                resource_id=1,
                data_table_count=1,
                reference_id=2306437,
            ),
            NpsPlannedFile(
                url="https://irma.nps.gov/DataStore/DownloadFile/2",
                filename="HUC.csv",
                relative_dir="pkg",
                resource_id=2,
                data_table_count=1,
                reference_id=663485,
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write_sidecars_for_files(1, folder, files, client)
            self.assertTrue((folder / "_project_files" / "data_table_info.csv").is_file())
            self.assertTrue((folder / "pkg" / "data_table_info.csv").is_file())


if __name__ == "__main__":
    unittest.main()
