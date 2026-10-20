"""Tests for FERC collected file writers."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from collectors.FercCollectedFiles import write_dataset_csv, write_dictionary_csv


class TestFercCollectedFiles(unittest.TestCase):
    """Tests for CSV paging and dictionary columns."""

    def test_write_dataset_csv_pages_until_done(self) -> None:
        """Pages are concatenated and the header comes from the first row."""
        client = MagicMock()
        client.fetch_data_page.side_effect = [
            {"row_data": [{"Name": "One"}], "has_more": True},
            {"row_data": [{"Name": "Two"}], "has_more": False},
        ]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "dataset.csv"
            written = write_dataset_csv(path, client, 33, page_size=1, pause_sec=0)
            with path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.reader(handle))

        self.assertEqual(written, 2)
        self.assertEqual(rows, [["Name"], ["One"], ["Two"]])
        self.assertEqual(client.fetch_data_page.call_args_list[1].kwargs["offset"], 1)

    def test_dictionary_csv_keeps_embedded_columns(self) -> None:
        """Embedded dictionary fields are written ahead of API-only names."""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "dictionary.csv"
            write_dictionary_csv(
                path,
                [
                    {
                        "column_id": 1,
                        "attribute": "CID",
                        "mapping": "CID",
                        "sql_type": "STRING",
                        "description": "Company id",
                        "nullable": "Y",
                    }
                ],
            )
            text = path.read_text(encoding="utf-8-sig")

        self.assertIn("attribute,mapping,sql_type", text)
        self.assertIn("CID", text)
        self.assertTrue(text.startswith("\ufeff") or "column_id" in text.splitlines()[0])


class TestDetailsJson(unittest.TestCase):
    """Tests for the details file."""

    def test_write_details_json(self) -> None:
        """Details are pretty-printed JSON."""
        from collectors.FercCollectedFiles import write_details_json

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "details.json"
            write_details_json(path, {"row_count": 3})
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["row_count"], 3)


if __name__ == "__main__":
    unittest.main()
