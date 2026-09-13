"""Tests for SSA catalog JSON-LD helpers."""

from __future__ import annotations

import unittest

from bs4 import BeautifulSoup

from collectors.SsaCatalogJsonLd import (
    format_from_encoding,
    geographic_label,
    json_ld_dataset,
    temporal_fields,
)


class TestSsaCatalogJsonLd(unittest.TestCase):
    """Tests for JSON-LD parsing helpers."""

    def test_format_from_encoding(self) -> None:
        """Map MIME types and URL suffixes to short format tokens."""
        self.assertEqual(
            format_from_encoding("application/zip", "https://x/names.zip"),
            "ZIP",
        )
        self.assertEqual(format_from_encoding("", "https://x/table.xml"), "XML")
        self.assertEqual(format_from_encoding("text/html", "https://x/a.html"), "HTML")

    def test_json_ld_dataset_reads_script(self) -> None:
        """Parse a Dataset object from an ld+json script tag."""
        soup = BeautifulSoup(
            """<script type="application/ld+json">
            {"@type":"Dataset","name":"Baby Names","identifier":"US-GOV-SSA-338"}
            </script>""",
            "html.parser",
        )
        dataset = json_ld_dataset(soup)
        self.assertEqual(dataset.get("identifier"), "US-GOV-SSA-338")

    def test_temporal_fields_from_coverage(self) -> None:
        """Split ISO interval coverage into start and end."""
        fields = temporal_fields("", {"temporalCoverage": "1880/2025"})
        self.assertEqual(fields["time_start"], "1880")
        self.assertEqual(fields["time_end"], "2025")

    def test_geographic_label_from_location_list(self) -> None:
        """Location arrays flatten to prefLabel / name values."""
        self.assertEqual(
            geographic_label(
                [{"@type": "Location", "prefLabel": "United States"}]
            ),
            "United States",
        )


if __name__ == "__main__":
    unittest.main()
