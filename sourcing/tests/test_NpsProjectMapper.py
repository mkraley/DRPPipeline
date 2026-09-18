"""Tests for IRMA Project → DataLumos field mapping."""

from __future__ import annotations

import unittest

from sourcing.NpsProjectMapper import (
    AGENCY,
    OFFICE,
    build_candidate_row,
    profile_keywords,
)


def _project_profile(*, public_product: bool) -> dict:
    """Build a minimal Project profile for mapper tests."""
    product = {
        "referenceId": 2001,
        "title": "Galax Database",
        "referenceType": "Relational Database",
        "fileCount": 2,
        "fileAccess": "Public" if public_product else "Restricted",
        "visibility": "Public",
    }
    return {
        "referenceId": 2268446,
        "visibility": "Public",
        "bibliography": {
            "title": "APHN Galax Monitoring",
            "abstract": "<p>Counts of galax.</p>",
        },
        "keywords": {"keyword": [{"keyword": "plants"}, {"keyword": "galax"}]},
        "filesAndLinks": [],
        "products": [product],
    }


class TestNpsProjectMapper(unittest.TestCase):
    """Tests for candidate-row construction."""

    def test_build_candidate_row_includes_breadcrumb_and_products(self) -> None:
        """Public products become folders; summary includes the breadcrumb."""
        row = build_candidate_row(
            collection_id=9688,
            collection_title="IMD Programs",
            program_id=2310251,
            program_title="APHN",
            profile=_project_profile(public_product=True),
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["agency"], AGENCY)
        self.assertEqual(row["office"], OFFICE)
        self.assertEqual(row["irma_project_id"], 2268446)
        self.assertEqual(row["public_file_count"], 2)
        self.assertEqual(len(row["products"]), 1)
        self.assertIn("Collection 9688: IMD Programs", row["breadcrumb"])
        self.assertIn("APHN Galax Monitoring", row["summary"])
        self.assertIn("Counts of galax.", row["summary"])
        self.assertEqual(row["keywords"], "plants, galax")

    def test_build_candidate_row_skips_projects_without_public_files(self) -> None:
        """Restricted-only products do not create a sourcing row."""
        row = build_candidate_row(
            collection_id=9688,
            collection_title="IMD Programs",
            program_id=2310251,
            program_title="APHN",
            profile=_project_profile(public_product=False),
        )
        self.assertIsNone(row)

    def test_profile_keywords_dedupes(self) -> None:
        """Repeated keyword strings are stored once."""
        self.assertEqual(
            profile_keywords({"keywords": [{"keyword": "a"}, {"keyword": "a"}]}),
            "a",
        )


if __name__ == "__main__":
    unittest.main()
