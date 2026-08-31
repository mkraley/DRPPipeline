"""Tests for BtsMetadataExtractor."""

from __future__ import annotations

import unittest
from pathlib import Path

from collectors.BtsMetadataExtractor import (
    infer_data_types,
    parse_detail_page,
    parse_download_files,
    record_id_from_source_url,
    _abstract_text,
    _temporal_range,
)
from bs4 import BeautifulSoup

_FIXTURE = Path(__file__).parent / "fixtures" / "bts_detail_54854.html"


class TestBtsMetadataExtractor(unittest.TestCase):
    """Tests for ROSA P HTML parsing helpers."""

    @classmethod
    def setUpClass(cls) -> None:
        """Load the shared HTML fixture once."""
        cls._html = _FIXTURE.read_text(encoding="utf-8")
        cls._url = "https://rosap.ntl.bts.gov/view/dot/54854"

    def test_record_id_from_source_url(self) -> None:
        """Extract numeric ids from ROSA P view URLs."""
        self.assertEqual(
            record_id_from_source_url("https://rosap.ntl.bts.gov/view/dot/54854"),
            "54854",
        )
        self.assertIsNone(record_id_from_source_url("https://example.com/"))

    def test_parse_detail_page_maps_metadata(self) -> None:
        """Parse title, summary, keywords, dates, and notes from fixture HTML."""
        metadata = parse_detail_page(self._html, self._url)
        self.assertIn("Nonattainment Areas", metadata["title"])
        self.assertIn("EPA", metadata["summary"])
        self.assertIn("Air Quality Management", metadata["keywords"])
        self.assertEqual(metadata["time_start"], "2004-01-01")
        self.assertEqual(metadata["time_end"], "2026-01-01")
        self.assertEqual(metadata["geographic_coverage"], "United States")
        self.assertIn("DOI:", metadata["collection_notes"])
        self.assertEqual(metadata["agency"], "Bureau of Transportation Statistics")
        self.assertIn("GIS", metadata["data_types"])

    def test_abstract_preserves_paragraph_breaks(self) -> None:
        """Abstract text keeps paragraph breaks from ``<br/>`` separators."""
        html = """
        <div class="bookDetailsData collapse pt-3" id="collapseDetails">
            First paragraph about NTAD databases.
            <br/> <br/>
            Second paragraph about shapefile format.
            <br/> <br/>
            Third paragraph about GIS and dBASE files.
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        summary = _abstract_text(soup)
        paragraphs = [part for part in summary.split("\n\n") if part]
        self.assertEqual(len(paragraphs), 3)
        self.assertIn("First paragraph", paragraphs[0])
        self.assertIn("shapefile", paragraphs[1])
        self.assertIn("dBASE", paragraphs[2])

    def test_temporal_range_present_sets_end_to_2026(self) -> None:
        """YYYY-Present ranges use 2026-01-01 as time_end."""
        result = _temporal_range(
            "NTAD Intermodal Facilities 2023-Present [dataset]",
            "2023-06-15",
            "",
        )
        self.assertEqual(result["time_start"], "2023-01-01")
        self.assertEqual(result["time_end"], "2026-01-01")

    def test_temporal_range_without_present_pairs_end_to_start(self) -> None:
        """Single publication dates copy time_end from time_start."""
        result = _temporal_range(
            "National Transportation Atlas Databases: 2003",
            "2003-01-01",
            "A nationwide geographic database.",
        )
        self.assertEqual(result["time_start"], "2003-01-01")
        self.assertEqual(result["time_end"], "2003-01-01")

    def test_temporal_range_present_word_uses_2026_end(self) -> None:
        """Standalone Present wording still sets time_end to 2026-01-01."""
        result = _temporal_range(
            "NTAD dataset",
            "2010-05-01",
            "Layers are updated through the Present.",
        )
        self.assertEqual(result["time_start"], "2010-05-01")
        self.assertEqual(result["time_end"], "2026-01-01")

    def test_parse_download_files_includes_main_and_supporting(self) -> None:
        """Collect the main ZIP plus supporting files from the fixture."""
        files = parse_download_files(self._html, self._url)
        main_files = [entry for entry in files if entry.is_main]
        supporting = [entry for entry in files if not entry.is_main]
        self.assertEqual(len(main_files), 1)
        self.assertTrue(main_files[0].url.endswith("dot_54854_DS1.zip"))
        self.assertEqual(main_files[0].size_bytes, int(354.66 * 1024**2))
        labels = {entry.label for entry in supporting}
        self.assertIn("README File", labels)
        self.assertIn("DCAT-US Metadata File", labels)

    def test_infer_data_types_detects_gis(self) -> None:
        """GIS-related subject terms map to the GIS data type."""
        result = infer_data_types(
            "NTAD dataset",
            "shapefile format",
            "Geographic Information Systems",
            "ZIP",
        )
        self.assertEqual(result, "GIS")

    def test_infer_data_types_uses_archive_extensions(self) -> None:
        """Shapefile extensions inside archives infer GIS data type."""
        result = infer_data_types("", "", "", "ZIP", file_extensions={"shp", "dbf"})
        self.assertEqual(result, "GIS")


if __name__ == "__main__":
    unittest.main()
