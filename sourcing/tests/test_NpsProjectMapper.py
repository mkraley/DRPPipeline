"""Tests for IRMA Project → DataLumos field mapping."""

from __future__ import annotations

import unittest

from sourcing.NpsProfileMetadata import AGENCY, OFFICE
from sourcing.NpsProjectMapper import build_candidate_row, profile_keywords

_NC_WKT = (
    "POLYGON ((-79.1 35.5, -78.5 35.5, -78.5 36.0, -79.1 36.0, -79.1 35.5))"
)


def _project_profile(*, public_product: bool) -> dict:
    """Build a Project profile with landing-page extras for mapper tests."""
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
        "citation": "NPS. 2013. APHN Galax Monitoring.",
        "bibliography": {
            "title": "APHN Galax Monitoring",
            "abstract": "<p>Counts of galax.</p>",
            "publisher": {"publisherName": "National Park Service"},
            "notes": "Field protocol notes.",
            "contentBegin": {"year": 2013, "precision": "YYYY", "yyyymmdd": "2013-01-01"},
            "contacts": [
                {
                    "contactType": "Lead(s)",
                    "contacts": [
                        {
                            "firstName": "Joe",
                            "primaryName": "Smith",
                            "affiliation": "NPS",
                        }
                    ],
                },
                {
                    "contactType": "Steward(s)",
                    "contacts": [
                        {
                            "firstName": "Ann",
                            "primaryName": "Lee",
                            "affiliation": "APHN",
                        }
                    ],
                },
            ],
        },
        "keywords": {"keyword": [{"keyword": "plants"}, {"keyword": "galax"}]},
        "units": [{"unitCode": "BISO", "unitName": "Big South Fork"}],
        "boundingBoxes": [{"wkt": _NC_WKT}],
        "filesAndLinks": [],
        "products": [product],
    }


class TestNpsProjectMapper(unittest.TestCase):
    """Tests for candidate-row construction."""

    def test_build_candidate_row_maps_agency_summary_dates_and_geo(self) -> None:
        """DOI/NPS fields, landing extras in summary, hierarchy only in notes."""
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
        self.assertEqual(row["agency"], "Department of the Interior")
        self.assertEqual(row["office"], OFFICE)
        self.assertEqual(row["office"], "National Park Service")
        self.assertEqual(row["irma_project_id"], 2268446)
        self.assertEqual(row["public_file_count"], 2)
        self.assertEqual(len(row["products"]), 1)
        self.assertIn("Collection 9688: IMD Programs", row["breadcrumb"])
        self.assertIn("Collection 9688: IMD Programs", row["collection_notes"])
        self.assertNotIn("Collection 9688", row["summary"])
        self.assertIn("Counts of galax.", row["summary"])
        self.assertIn("Leads", row["summary"])
        self.assertIn("Joe Smith", row["summary"])
        self.assertIn("Stewards", row["summary"])
        self.assertIn("Publisher", row["summary"])
        self.assertIn("Notes", row["summary"])
        self.assertEqual(row["keywords"], "plants, galax")
        self.assertEqual(row["time_start"], "2013")
        self.assertEqual(row["time_end"], "2013")
        self.assertIn("North Carolina", row["geographic_coverage"])

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
