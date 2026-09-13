"""Tests for SSA Complete Metadata table parsing."""

from __future__ import annotations

import unittest

from bs4 import BeautifulSoup

from collectors.SsaCompleteMetadata import coverage_from_complete_metadata

_COMPLETE_METADATA_HTML = """
<html><body>
<details>
    <summary>
        <h2 class="complete-metadata-heading">Complete Metadata</h2>
    </summary>
    <table class="metadata-table">
        <tr>
            <th scope="row">spatial</th>
            <td>
                <pre class="json">[ { "@type" : "Location" , "prefLabel" : "United States" } ]</pre>
            </td>
        </tr>
        <tr>
            <th scope="row">temporal</th>
            <td>
                <pre class="json">[ { "@type" : "PeriodOfTime" , "endDate" : "2025-12-31" , "startDate" : "1880-01-01" } ]</pre>
            </td>
        </tr>
    </table>
</details>
</body></html>
"""


class TestSsaCompleteMetadata(unittest.TestCase):
    """Tests for DCAT Complete Metadata coverage fields."""

    def test_coverage_from_temporal_and_spatial_json(self) -> None:
        """PeriodOfTime and Location JSON become storage coverage fields."""
        soup = BeautifulSoup(_COMPLETE_METADATA_HTML, "html.parser")
        coverage = coverage_from_complete_metadata(soup)
        self.assertEqual(coverage["time_start"], "1880-01-01")
        self.assertEqual(coverage["time_end"], "2025-12-31")
        self.assertEqual(coverage["geographic_coverage"], "United States")

    def test_missing_section_returns_empty(self) -> None:
        """Pages without Complete Metadata yield no coverage fields."""
        soup = BeautifulSoup("<html><body><h1>No metadata</h1></body></html>", "html.parser")
        self.assertEqual(coverage_from_complete_metadata(soup), {})


if __name__ == "__main__":
    unittest.main()
