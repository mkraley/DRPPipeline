"""Tests for NPS download planning helpers."""

from __future__ import annotations

import unittest

from collectors.NpsDownloadPlan import (
    planned_files_for_profile,
    product_folder_name,
    sidecar_filename,
)


class TestNpsDownloadPlan(unittest.TestCase):
    """Tests for product folders and planned Digital Files."""

    def test_product_folder_name_includes_id(self) -> None:
        """Folder names start with the IRMA Product id."""
        name = product_folder_name(663485, "Mammal inventory: Blue Ridge?")
        self.assertTrue(name.startswith("663485_"))
        self.assertNotIn("?", name)

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
