"""Tests for EpaCollector thin wrapper and EPA agency labeling."""

from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from collectors.ContentLengthProbe import ContentLengthProbe
from collectors.EpaCollector import EpaCollector
from sourcing.EpaSourcing import AGENCY
from utils.Args import Args
from utils.Logger import Logger

_URL = "https://catalog.data.gov/dataset/air-quality-system-aqs"


class TestEpaCollector(unittest.TestCase):
    """Tests for EPA Data.gov collector wiring."""

    def setUp(self) -> None:
        """Initialize Args and a collector instance."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "noop"]
        Args.initialize()
        Args._config["base_output_dir"] = str(Path(__file__).parent / "_tmp_epa_output")
        Logger.initialize(log_level="WARNING")
        self.collector = EpaCollector(headless=True)

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    def test_uses_epa_agency_labels(self) -> None:
        """Wrapper configures Environmental Protection Agency labels."""
        self.assertEqual(self.collector._agency, AGENCY)
        self.assertEqual(self.collector._office, AGENCY)
        self.assertEqual(self.collector._source_label, "EPA")

    @patch("collectors.DataGovCollector.record_error")
    def test_collect_rejects_non_catalog_url(self, mock_error: MagicMock) -> None:
        """Non-catalog URLs are rejected before fetch."""
        self.collector._page_downloader = MagicMock()
        result = self.collector._collect("https://www.epa.gov/data/", 1, {})
        self.assertEqual(result, {})
        mock_error.assert_called()

    @patch("collectors.DataGovCollector.create_output_folder")
    def test_collect_stamps_epa_agency(self, mock_create_folder: MagicMock) -> None:
        """Parsed catalog metadata uses EPA agency/office."""
        folder = Path(__file__).parent / "_tmp_epa_collect"
        folder.mkdir(exist_ok=True)
        mock_create_folder.return_value = folder
        page_downloader = MagicMock()
        page_downloader.fetch_page_html.return_value = (
            200,
            """
            <html><body>
            <script type="application/ld+json">
            {"@type":"Dataset","name":"Air Quality",
             "distribution":[{"contentUrl":"https://www.epa.gov/data/air.csv",
                              "encodingFormat":"text/csv"}]}
            </script>
            <h1>Air Quality</h1>
            </body></html>
            """,
            "text/html",
            False,
        )
        page_downloader.url_to_pdf.return_value = True
        page_downloader.fetch_content_length.return_value = 4
        page_downloader.probe_download.return_value = ContentLengthProbe(size_bytes=4)

        def _write(url: str, dest: Path) -> tuple[int, bool]:
            dest.write_bytes(b"a,b\n")
            return 4, True

        page_downloader.download_file.side_effect = _write
        self.collector._page_downloader = page_downloader
        try:
            result = self.collector._collect(_URL, 2, {})
            self.assertEqual(result.get("title"), "Air Quality")
            self.assertEqual(result.get("agency"), AGENCY)
            self.assertEqual(result.get("office"), AGENCY)
            self.assertTrue((folder / "air.csv").is_file())
            warmup_urls = [
                call.args[0]
                for call in page_downloader.fetch_page_html.call_args_list
            ]
            self.assertEqual(warmup_urls[0], "https://www.epa.gov/")
        finally:
            shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
