"""Tests for AirData series titles and storage fields."""

from __future__ import annotations

import unittest

from sourcing.AqsFile import AqsFile
from sourcing.AqsSeries import AQS_SUMMARY_NOTE, AqsSeries, INDEX_FILENAME
from utils.datalumos_data_types import DATA_TYPE_AGGREGATE, DATA_TYPE_OBSERVATIONAL


def _series() -> AqsSeries:
    """Return a two-year ozone column with one empty year omitted."""
    return AqsSeries(
        "hourly_44201",
        "Hourly Data",
        "Ozone (44201)",
        (
            AqsFile("hourly_44201_1980.zip", 10, 20, "data"),
            AqsFile("hourly_44201_2026.zip", 30, 40, "data"),
        ),
        omitted_empty=2,
    )


class TestAqsSeries(unittest.TestCase):
    """Storage fields derived from a download-page column."""

    def test_storage_fields_cover_the_year_span(self) -> None:
        """Hourly ozone is observational data from the first year through the last."""
        fields = _series().storage_fields()
        self.assertEqual(fields["title"], "Air Data Hourly Data - Ozone (44201)")
        self.assertEqual(fields["office"], "Environmental Protection Agency")
        self.assertIn(AQS_SUMMARY_NOTE, fields["summary"])
        self.assertEqual(fields["collection_notes"], "")
        self.assertEqual(fields["time_start"], "1980")
        self.assertEqual(fields["time_end"], "2026")
        self.assertEqual(fields["data_types"], DATA_TYPE_OBSERVATIONAL)
        self.assertIn("44201", fields["keywords"])
        self.assertIn("2 files listed as 0 KB", fields["summary"])
        self.assertEqual(fields["status"], "sourced")

    def test_annual_series_is_aggregate_data(self) -> None:
        """Annual summary columns use the aggregate data type."""
        series = AqsSeries(
            "annual_aqi_by_county",
            "Annual Summary Data",
            "AQI by County",
            (AqsFile("annual_aqi_by_county_2024.zip", 1, 2, "data"),),
        )
        self.assertEqual(series.data_type(), DATA_TYPE_AGGREGATE)
        self.assertEqual(series.source_url().split("#")[-1], "annual_aqi_by_county")

    def test_site_project_includes_the_file_list(self) -> None:
        """The site project packages the download-page file list."""
        series = AqsSeries(
            "sites",
            "Site and Monitor Descriptions",
            "",
            (AqsFile("aqs_sites.zip", 1, 2, "data"),),
        )
        names = [item.filename for item in series.packaged_files()]
        self.assertIn(INDEX_FILENAME, names)
        self.assertNotIn("time_start", series.storage_fields())


if __name__ == "__main__":
    unittest.main()
