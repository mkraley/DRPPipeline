"""Tests for collecting one EQR year range."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from collectors.EqrCollector import EqrCollector
from collectors.EqrDictionary import DICTIONARY_NAME
from collectors.EqrProjectRange import project_ranges
from collectors.EqrZipLink import EqrZipLink
from collectors.FercCollectedFiles import LANDING_PDF_NAME
from collectors.FercCollector import FercCollector
from storage import Storage
from storage.ProjectFileStore import ProjectFileStore
from utils.Args import Args
from utils.Logger import Logger
from utils.inventory_status import STATUS_COLLECTED_LARGE

_ZIP_BYTES = b"csv-zip"
_GIB = 1024**3


class TestEqrCollector(unittest.TestCase):
    """Collection keeps CSV zips for the span and defers past 1 GiB."""

    def setUp(self) -> None:
        """Point collection at a temporary database and folder."""
        self._argv = sys.argv.copy()
        sys.argv = ["test", "collect"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.temp_dir = Path(tempfile.mkdtemp())
        Args._config["base_output_dir"] = str(self.temp_dir)
        Args._config["google_sheet_name"] = "FERC"
        Storage.reset()
        self.storage = Storage.initialize("StorageSQLLite", db_path=self.temp_dir / "test.db")

    def tearDown(self) -> None:
        """Close the database and remove the temp folder."""
        self.storage.close()
        Storage.reset()
        sys.argv = self._argv
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_collect_downloads_in_span_and_defers_the_oversized_zip(self) -> None:
        """The first small zip is saved; a later multi-gigabyte zip waits for resume."""
        span = project_ranges()[0]
        small = EqrZipLink("CSV_2013_Q3.zip", "https://example.test/CSV/CSV_2013_Q3.zip", len(_ZIP_BYTES))
        huge = EqrZipLink("CSV_2018_Q4.zip", "https://example.test/CSV/CSV_2018_Q4.zip", 2 * _GIB)
        other = EqrZipLink("CSV_2021_Q1.zip", "https://example.test/CSV/CSV_2021_Q1.zip", 10)
        pages = MagicMock()
        pages.url_html_to_pdf.side_effect = lambda _url, _html, path: path.write_bytes(b"%PDF") or True
        collector = EqrCollector(
            page_downloader=pages,
            link_source=lambda: [small, huge, other],
            download_file=_save_bytes,
            explain_html='<a href="https://example.test/dictionary.pdf">Data Dictionary V3.5</a>',
        )
        folder = self.temp_dir / "FERC000007"
        folder.mkdir()
        (folder / "keep.txt").write_text("keep", encoding="utf-8")

        result = collector.collect(span.source_url(), 7, {"title": span.title(), "summary": span.summary()})

        self.assertEqual((folder / "keep.txt").read_text(encoding="utf-8"), "keep")
        self.assertEqual((folder / "CSV_2013_Q3.zip").read_bytes(), _ZIP_BYTES)
        self.assertFalse((folder / "CSV_2018_Q4.zip").exists())
        self.assertFalse((folder / "CSV_2021_Q1.zip").exists())
        self.assertTrue((folder / LANDING_PDF_NAME).is_file())
        self.assertTrue((folder / DICTIONARY_NAME).is_file())
        self.assertEqual(result["status"], STATUS_COLLECTED_LARGE)
        self.assertEqual(result["time_start"], "2013-07-01")
        self.assertEqual(result["time_end"], "2018-12-31")
        self.assertIn("Electric Quarterly Report", result["keywords"])
        self.assertEqual(result["geographic_coverage"], "United States")
        rows = {row.relative_path: row for row in ProjectFileStore.from_storage().list_for_project(7)}
        self.assertTrue(rows["CSV_2013_Q3.zip"].downloaded)
        self.assertFalse(rows["CSV_2018_Q4.zip"].downloaded)
        self.assertNotIn("CSV_2021_Q1.zip", rows)
        pages.url_html_to_pdf.assert_called_once()
        pages.url_to_pdf.assert_not_called()

    def test_ferc_collector_sends_eqr_urls_to_the_eqr_collector(self) -> None:
        """A catalog lookup does not run for an EQR year-range URL."""
        catalog = MagicMock()
        datasets = MagicMock()
        collector = FercCollector(
            page_downloader=MagicMock(),
            dataset_client=datasets,
            catalog_client=catalog,
        )
        url = project_ranges()[2].source_url()
        with patch(
            "collectors.EqrCollector.EqrCollector.collect",
            return_value={"status": STATUS_COLLECTED_LARGE},
        ) as collect:
            result = collector._collect(url, 9, {"title": "Electric Quarterly Report (CSV), 2021"})
        collect.assert_called_once()
        catalog.fetch_data_assets.assert_not_called()
        datasets.fetch_data_page.assert_not_called()
        self.assertEqual(result["status"], STATUS_COLLECTED_LARGE)


def _save_bytes(url: str, dest: Path) -> tuple[int, bool]:
    """Write a tiny stand-in for a zip or the dictionary PDF."""
    payload = _ZIP_BYTES if "CSV_" in url else b"%PDF-1.4"
    dest.write_bytes(payload)
    return len(payload), True


if __name__ == "__main__":
    unittest.main()
