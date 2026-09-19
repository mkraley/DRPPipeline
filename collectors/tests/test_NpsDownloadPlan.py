"""Tests for NPS download planning helpers."""

from __future__ import annotations

import unittest

from collectors.NpsDownloadPlan import (
    planned_files_for_profile,
    product_folder_name,
    sidecar_filename,
    unique_product_folder_name,
)


class TestNpsDownloadPlan(unittest.TestCase):
    """Tests for product folders and planned Digital Files."""

    def test_product_folder_name_uses_title_only(self) -> None:
        """Folder names use the product title and omit the IRMA id."""
        name = product_folder_name("Mammal inventory: Blue Ridge?")
        self.assertNotIn("663485", name)
        self.assertFalse(name[:1].isdigit())
        self.assertNotIn("?", name)
        self.assertIn("Mammal", name)

    def test_unique_product_folder_name_disambiguates(self) -> None:
        """Duplicate titles get a numeric suffix instead of an IRMA id."""
        used: set[str] = set()
        first = unique_product_folder_name("Same Title", used)
        second = unique_product_folder_name("Same Title", used)
        self.assertNotEqual(first, second)
        self.assertTrue(second.startswith(first))

    def test_sidecar_filename(self) -> None:
        """Sidecars sit next to the CSV they describe."""
        self.assertEqual(sidecar_filename("HUC.csv"), "HUC_data_table_info.csv")

    def test_planned_files_skip_external_links_and_merge_holdings(self) -> None:
        """Only Digital Files are planned; holdings supply size and table count."""
        profile = {
            "referenceId": 2308545,
            "visibility": "Public",
            "filesAndLinks": [
                {
                    "fileId": 716591,
                    "resourceType": "Digital File",
                    "url": "https://irma.nps.gov/DataStore/DownloadFile/716591",
                    "fileName": "HUC.csv",
                },
                {
                    "resourceType": "External Link",
                    "url": "https://example.com",
                    "fileName": "website",
                },
            ],
        }
        holdings = [
            {
                "Id": 716591,
                "Url": "https://irma.nps.gov/DataStore/DownloadFile/716591",
                "FileDescription": "HUC.csv",
                "FileSize": 100,
                "DataTableCount": 2,
            }
        ]
        planned = planned_files_for_profile(profile, "2308545_pkg", holdings)
        self.assertEqual(len(planned), 1)
        self.assertEqual(planned[0].filename, "HUC.csv")
        self.assertEqual(planned[0].size_bytes, 100)
        self.assertEqual(planned[0].data_table_count, 2)
        self.assertEqual(planned[0].relative_dir, "2308545_pkg")


if __name__ == "__main__":
    unittest.main()
