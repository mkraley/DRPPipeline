"""Tests for EQR CSV zip link selection."""

from __future__ import annotations

import unittest

from collectors.EqrDictionary import dictionary_url_from_html
from collectors.EqrProjectRange import project_ranges
from collectors.EqrZipLink import EqrZipLink, csv_links_from_pairs, links_for_range
from collectors.EqrZipSize import zip_content_length

_TOKEN = "ABC"
_CSV = (
    f"https://eqrreportviewer.ferc.gov/DownloadRepositoryProd/{_TOKEN}/BulkNew/CSV/"
    "CSV_2013_Q3.zip"
)
_XML = (
    f"https://eqrreportviewer.ferc.gov/DownloadRepositoryProd/{_TOKEN}/BulkNew/XML/"
    "XML_2013_Q3.zip"
)


class TestEqrZipLink(unittest.TestCase):
    """The viewer lists CSV and XML; only CSV zips in the project span are kept."""

    def test_csv_links_drop_xml_copies(self) -> None:
        """An XML href is ignored even when it sits beside the CSV link."""
        links = csv_links_from_pairs(
            [
                ("CSV_2013_Q3.zip", _CSV),
                ("XML_2013_Q3.zip", _XML),
                ("CSV_2013_Q4.zip", _CSV.replace("Q3", "Q4")),
            ]
        )
        self.assertEqual([link.name for link in links], ["CSV_2013_Q3.zip", "CSV_2013_Q4.zip"])
        self.assertIn("/CSV/", links[0].url)

    def test_range_keeps_only_its_quarters(self) -> None:
        """2013 Q3 belongs to the first project and 2021 Q1 does not."""
        links = [
            EqrZipLink("CSV_2013_Q3.zip", _CSV, 10),
            EqrZipLink("CSV_2021_Q1.zip", _CSV.replace("2013_Q3", "2021_Q1"), 20),
        ]
        selected = links_for_range(links, project_ranges()[0])
        self.assertEqual([link.name for link in selected], ["CSV_2013_Q3.zip"])

    def test_dictionary_link_prefers_version_3_5(self) -> None:
        """The current CSV filings use the V3.5 dictionary, not the later XBRL one."""
        html = """
        <a href="https://elibrary.ferc.gov/eLibrary/filelist?accession_number=1">EQR Data Dictionary</a>
        <a href="https://www.ferc.gov/sites/default/files/2020-11/Data_Dictionary_V3_5_Clean.pdf">Data Dictionary V3.5</a>
        """
        self.assertTrue(dictionary_url_from_html(html).endswith("Data_Dictionary_V3_5_Clean.pdf"))

    def test_zip_size_reads_content_range(self) -> None:
        """A one-byte response reports the whole archive size."""

        class _Response:
            status_code = 206
            headers = {"Content-Range": "bytes 0-0/1200", "Content-Length": "1"}

            def close(self) -> None:
                return None

        size = zip_content_length("https://example.test/CSV_2013_Q3.zip", getter=lambda *_a, **_k: _Response())
        self.assertEqual(size, 1200)


if __name__ == "__main__":
    unittest.main()
