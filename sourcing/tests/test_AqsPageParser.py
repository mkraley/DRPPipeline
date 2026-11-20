"""Tests for the AirData download-page parser."""

from __future__ import annotations

import unittest

from sourcing.AqsPageParser import AqsPageParser
from sourcing.AqsSeries import FORMATS_FILENAME

_PAGE = """
<h2>Site and Monitor Descriptions</h2>
<a href="aqs_sites.zip">Site Listing</a> (10 Rows, 20 KB)<br>
<a href="aqs_monitors.zip">Monitor Listing</a> (30 Rows, 40 KB)<br>
<h2>Annual Summary Data</h2>
<table><table>
<tr><th>Year</th><th>Concentration by Monitor</th><th>AQI by CBSA</th></tr>
<tr>
<td>2024</td>
<td><a href="annual_conc_by_monitor_2024.zip">f</a><br>5 Rows<br>12 KB<br>
<a href="Data_Advisory_PM25_88101_Pregen_Files.pdf">PM2.5</a></td>
<td><a href="annual_aqi_by_cbsa_2024.zip">f</a><br>1 Rows<br>2 KB</td>
</tr>
<tr>
<td>1990</td>
<td><a href="annual_conc_by_monitor_1990.zip">f</a><br>0 Rows<br>0 KB</td>
<td><a href="annual_aqi_by_cbsa_1990.zip">f</a><br>1 Rows<br>1 KB</td>
</tr>
</table></table>
<h2>Daily Summary Data</h2>
<h3>Criteria Gases</h3>
<table>
<tr><th>Year</th><th>Ozone (44201)</th></tr>
<tr><td>2024</td><td><a href="daily_44201_2024.zip">f</a><br>8 Rows<br>9 KB</td></tr>
</table>
<h2>Daily AQI</h2>
<table>
<tr><th>Year</th><th>Daily AQI by CBSA </th></tr>
<tr><td>2024</td><td><a href="daily_aqi_by_cbsa_2024.zip">f</a><br>3 Rows<br>4 KB</td></tr>
</table>
<h2>Hourly Data</h2>
<table>
<tr><th>Year</th><th>Ozone (44201)</th></tr>
<tr><td>2024</td><td><a href="hourly_44201_2024.zip">f</a><br>8 Rows<br>9 KB</td></tr>
</table>
<h2>Blanks Data</h2>
<table>
<tr><td>2024</td><td><a href="blanks_all_2024.zip">f</a><br>8 Rows<br>9 KB</td></tr>
</table>
"""


class TestAqsPageParser(unittest.TestCase):
    """Parser coverage for columns, empty files, and extra PDFs."""

    def setUp(self) -> None:
        """Parse the fixture page once."""
        self.series = AqsPageParser().parse_html(_PAGE)
        self.by_id = {item.series_id: item for item in self.series}

    def test_columns_follow_page_order(self) -> None:
        """Each column becomes one series, in the order the page lists them."""
        self.assertEqual(
            [item.series_id for item in self.series],
            [
                "sites",
                "annual_conc_by_monitor",
                "annual_aqi_by_cbsa",
                "daily_44201",
                "daily_aqi_by_cbsa",
                "hourly_44201",
                "blanks_all",
            ],
        )

    def test_site_listing_keeps_both_zips(self) -> None:
        """Site and monitor descriptions are one project with both listings."""
        sites = self.by_id["sites"]
        names = [item.filename for item in sites.files]
        self.assertEqual(names, ["aqs_sites.zip", "aqs_monitors.zip"])
        self.assertEqual(sites.title(), "Site and Monitor Descriptions")

    def test_zero_kb_zip_is_omitted_and_advisory_is_kept(self) -> None:
        """A 0 KB year is counted as omitted, and the advisory PDF stays once."""
        column = self.by_id["annual_conc_by_monitor"]
        data = [item.filename for item in column.files if item.kind == "data"]
        advisories = [item.filename for item in column.files if item.kind == "advisory"]
        self.assertEqual(data, ["annual_conc_by_monitor_2024.zip"])
        self.assertEqual(advisories, ["Data_Advisory_PM25_88101_Pregen_Files.pdf"])
        self.assertEqual(column.omitted_empty, 1)
        self.assertIn(FORMATS_FILENAME, column.collection_notes())

    def test_repeated_pollutant_is_a_separate_series_per_table(self) -> None:
        """Daily and hourly ozone are different projects."""
        self.assertEqual(
            self.by_id["daily_44201"].title(),
            "Daily Summary Data - Ozone (44201)",
        )
        self.assertEqual(
            self.by_id["hourly_44201"].title(),
            "Hourly Data - Ozone (44201)",
        )
        self.assertEqual(self.by_id["daily_aqi_by_cbsa"].title(), "Daily AQI by CBSA")
        self.assertEqual(self.by_id["blanks_all"].title(), "Blanks Data")


if __name__ == "__main__":
    unittest.main()
