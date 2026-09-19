"""Tests for recursive IRMA public Digital File counts."""

from __future__ import annotations

import unittest

from sourcing.NpsPublicFileCount import recursive_public_file_count

_PUBLIC_FILE = {
    "resourceType": "Digital File",
    "url": "https://irma.nps.gov/DataStore/DownloadFile/1",
    "fileName": "a.csv",
}


class TestNpsPublicFileCount(unittest.TestCase):
    """Tests for Project + nested Product file totals."""

    def test_sums_project_files_and_public_product_file_counts(self) -> None:
        """Direct Project files plus public Product fileCount values."""
        profile = {
            "referenceId": 1,
            "visibility": "Public",
            "filesAndLinks": [_PUBLIC_FILE],
            "products": [
                {
                    "referenceId": 2,
                    "visibility": "Public",
                    "fileAccess": "Public",
                    "fileCount": 2,
                },
                {
                    "referenceId": 3,
                    "visibility": "Public",
                    "fileAccess": "Restricted",
                    "fileCount": 9,
                },
            ],
        }
        self.assertEqual(recursive_public_file_count(profile), 3)

    def test_includes_nested_public_products(self) -> None:
        """Products nested under other Products are included."""
        nested = {
            "referenceId": 30,
            "visibility": "Public",
            "fileAccess": "Public",
            "fileCount": 4,
        }
        child = {
            "referenceId": 20,
            "visibility": "Public",
            "fileAccess": "Public",
            "fileCount": 2,
            "products": [nested],
        }
        profile = {
            "referenceId": 10,
            "visibility": "Public",
            "filesAndLinks": [],
            "products": [child],
        }
        self.assertEqual(recursive_public_file_count(profile), 6)

    def test_counts_linked_resources_on_product_summaries(self) -> None:
        """Product linkedResources with download URLs beat fileCount."""
        profile = {
            "referenceId": 10,
            "visibility": "Public",
            "products": [
                {
                    "referenceId": 20,
                    "visibility": "Public",
                    "fileAccess": "Public",
                    "fileCount": 9,
                    "linkedResources": [
                        _PUBLIC_FILE,
                        {**_PUBLIC_FILE, "url": "https://irma.nps.gov/DataStore/DownloadFile/2"},
                    ],
                }
            ],
        }
        self.assertEqual(recursive_public_file_count(profile), 2)


if __name__ == "__main__":
    unittest.main()
