"""Tests for SsaMetadataExtractor."""

from __future__ import annotations

import unittest
from pathlib import Path

from collectors.SsaMetadataExtractor import (
    filename_from_url,
    parse_catalog_page,
    parse_download_files,
    parse_html_resources,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "ssa_catalog_baby_names.html"
_URL = (
    "https://catalog.data.gov/dataset/"
    "baby-names-from-social-security-card-applications-national-data"
)


class TestSsaMetadataExtractor(unittest.TestCase):
    """Tests for catalog.data.gov SSA page parsing."""

    @classmethod
    def setUpClass(cls) -> None:
        """Load the shared HTML fixture once."""
        cls._html = _FIXTURE.read_text(encoding="utf-8")

    def test_filename_from_url(self) -> None:
        """Use the URL path tail as the on-disk name."""
        self.assertEqual(
            filename_from_url("https://www.ssa.gov/oact/babynames/names.zip"),
            "names.zip",
        )
        self.assertEqual(filename_from_url("https://www.ssa.gov/data/"), "download")

    def test_parse_catalog_page_maps_metadata(self) -> None:
        """Parse title, summary, keywords, dates, and identifier notes."""
        metadata = parse_catalog_page(self._html, _URL)
        self.assertIn("Baby Names", metadata["title"])
        self.assertIn("100 percent sample", metadata["summary"])
        self.assertIn("Baby names", metadata["keywords"])
        self.assertEqual(metadata["time_start"], "1880-01-01")
        self.assertEqual(metadata["time_end"], "2025-12-31")
        self.assertEqual(metadata["geographic_coverage"], "United States")
        self.assertIn("US-GOV-SSA-338", metadata["collection_notes"])
        self.assertEqual(metadata["agency"], "Social Security Administration")

    def test_parse_download_files_skips_html(self) -> None:
        """HTML landing pages are omitted; ZIP remains."""
        files = parse_download_files(self._html, _URL)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].url, "https://www.ssa.gov/oact/babynames/names.zip")
        self.assertEqual(files[0].filename, "names.zip")
        self.assertEqual(len(parse_html_resources(self._html, _URL)), 1)
        self.assertEqual(
            parse_html_resources(self._html, _URL)[0].url,
            "https://www.ssa.gov/oact/babynames/index.html",
        )

    def test_json_ld_fallback_when_complete_metadata_missing(self) -> None:
        """JSON-LD coverage is used when Complete Metadata is absent."""
        html = """
        <html><body>
        <script type="application/ld+json">
        {"@type":"Dataset","name":"Baby Names",
         "spatial":"United States","temporalCoverage":"1880/2025"}
        </script>
        <h1>Baby Names</h1>
        </body></html>
        """
        metadata = parse_catalog_page(html, _URL)
        self.assertEqual(metadata["time_start"], "1880")
        self.assertEqual(metadata["time_end"], "2025")
        self.assertEqual(metadata["geographic_coverage"], "United States")

    def test_html_only_page_has_no_downloads(self) -> None:
        """A page with only HTML resources yields no files."""
        html = """
        <html><body>
        <script type="application/ld+json">
        {"@type":"Dataset","name":"Index",
         "distribution":[{"contentUrl":"https://www.ssa.gov/x.html",
                          "encodingFormat":"text/html"}]}
        </script>
        <h1>Index</h1>
        </body></html>
        """
        files = parse_download_files(html, _URL)
        self.assertEqual(files, [])
        html_resources = parse_html_resources(html, _URL)
        self.assertEqual(len(html_resources), 1)
        self.assertEqual(html_resources[0].url, "https://www.ssa.gov/x.html")


if __name__ == "__main__":
    unittest.main()
