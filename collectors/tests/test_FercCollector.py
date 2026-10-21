"""Tests for FercCollector."""

from __future__ import annotations

import csv
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from collectors.FercCollectedFiles import DATASET_NAME, DETAILS_NAME, DICTIONARY_NAME, LANDING_PDF_NAME
from collectors.FercCollector import FercCollector
from utils.Args import Args
from utils.Logger import Logger

_URL = "https://data.ferc.gov/active-hydropower-projects/licensed-marine-and-hydrokinetic-projects"
_EMBEDDED = """
<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"dataDict":[
  {"attribute":"Project_Name","mapping":"Project Name","column_id":1,"sql_type":"STRING","description":"Name"}
]}}}</script>
"""


class TestFercCollector(unittest.TestCase):
    """Tests for collecting one FERC dataset."""

    def setUp(self) -> None:
        """Point output at a temporary folder."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "collect"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.temp_dir = Path(tempfile.mkdtemp())
        Args._config["base_output_dir"] = str(self.temp_dir)
        Args._config["google_sheet_name"] = "FERC"
        Args._config["ferc_request_delay"] = 0

    def tearDown(self) -> None:
        """Restore argv and remove the temp folder."""
        sys.argv = self._original_argv
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_collect_saves_pdf_csv_details_and_embedded_dictionary(self) -> None:
        """Embedded dictionary wins over the API dictionary."""
        pages = MagicMock()

        def _pdf(_url: str, path: Path) -> bool:
            path.write_bytes(b"%PDF-1.4")
            return True

        pages.url_to_pdf.side_effect = _pdf
        datasets = MagicMock()
        datasets.fetch_details.return_value = {"row_count": 3, "metadata": [{"id": 33}]}
        datasets.fetch_data_page.return_value = {
            "row_data": [{"Project_Name": "Igiugig"}],
            "has_more": False,
        }
        catalog = MagicMock()
        catalog.fetch_data_assets.return_value = [
            {
                "program_office": "Office of Energy Projects",
                "data-sets": [
                    {
                        "id": 33,
                        "title": "Licensed Marine and Hydrokinetic Projects",
                        "url": _URL,
                        "description": "Wave and current projects.",
                    }
                ],
            }
        ]
        collector = FercCollector(
            page_downloader=pages,
            dataset_client=datasets,
            catalog_client=catalog,
            html_fetcher=lambda _url: _EMBEDDED,
        )

        result = collector._collect(_URL, 7, {})

        folder = Path(result["folder_path"])
        self.assertTrue((folder / LANDING_PDF_NAME).is_file())
        self.assertEqual(json.loads((folder / DETAILS_NAME).read_text(encoding="utf-8"))["row_count"], 3)
        with (folder / DATASET_NAME).open(encoding="utf-8-sig", newline="") as handle:
            self.assertEqual(list(csv.reader(handle)), [["Project_Name"], ["Igiugig"]])
        dictionary = (folder / DICTIONARY_NAME).read_text(encoding="utf-8-sig")
        self.assertIn("attribute", dictionary)
        self.assertIn("Project Name", dictionary)
        datasets.fetch_dictionary.assert_not_called()
        self.assertEqual(result["num_files"], 4)
        self.assertEqual(result["extensions"], "csv, json, pdf")

    def test_collect_uses_api_dictionary_when_page_has_none(self) -> None:
        """A null embedded dictionary falls back to the API dictionary."""
        pages = MagicMock()
        pages.url_to_pdf.side_effect = lambda _url, path: path.write_bytes(b"%PDF") or True
        datasets = MagicMock()
        datasets.fetch_details.return_value = None
        datasets.fetch_dictionary.return_value = [
            {"column_id": 1, "column_name": "Project_Name", "data_type": "STRING", "description": "Name"}
        ]
        datasets.fetch_data_page.return_value = {"row_data": [{"Project_Name": "A"}], "has_more": False}
        catalog = MagicMock()
        catalog.fetch_data_assets.return_value = [
            {
                "data-sets": [
                    {"id": 33, "title": "Licensed", "url": _URL, "description": ""}
                ]
            }
        ]
        collector = FercCollector(
            page_downloader=pages,
            dataset_client=datasets,
            catalog_client=catalog,
            html_fetcher=lambda _url: "<html></html>",
        )

        result = collector._collect(_URL, 7, {})

        folder = Path(result["folder_path"])
        self.assertFalse((folder / DETAILS_NAME).exists())
        text = (folder / DICTIONARY_NAME).read_text(encoding="utf-8-sig")
        self.assertIn("column_name", text)
        self.assertIn("Project_Name", text)
        datasets.fetch_dictionary.assert_called_once_with(33)

    def test_collect_infers_metadata_from_summary_and_dataset(self) -> None:
        """Fill metadata uses the stored summary and the dataset just written."""
        pages = MagicMock()
        pages.url_to_pdf.side_effect = lambda _url, path: path.write_bytes(b"%PDF") or True
        datasets = MagicMock()
        datasets.fetch_details.return_value = None
        datasets.fetch_dictionary.return_value = None
        datasets.fetch_data_page.return_value = {
            "row_data": [
                {"State": "AK", "Issuance_Date": "2019-05-23"},
                {"State": "OR", "Issuance_Date": "2021-03-01"},
            ],
            "has_more": False,
        }
        catalog = MagicMock()
        catalog.fetch_data_assets.return_value = [
            {"data-sets": [{"id": 33, "title": "Licensed", "url": _URL, "description": ""}]}
        ]
        collector = FercCollector(
            page_downloader=pages,
            dataset_client=datasets,
            catalog_client=catalog,
            html_fetcher=lambda _url: "<html></html>",
        )

        result = collector._collect(
            _URL,
            7,
            {
                "title": "Licensed Marine and Hydrokinetic Projects",
                "summary": "Hydrokinetic projects in the United States.",
            },
        )

        self.assertEqual(result["geographic_coverage"], "United States")
        self.assertEqual(result["time_start"], "2019-05-23")
        self.assertEqual(result["time_end"], "2021-03-01")
        self.assertIn("hydrokinetic", result["keywords"])


if __name__ == "__main__":
    unittest.main()
