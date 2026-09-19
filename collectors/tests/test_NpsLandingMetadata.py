"""Tests for IRMA landing-page metadata JSON files."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from collectors.NpsLandingMetadata import (
    PRODUCT_METADATA_NAME,
    landing_metadata_dict,
    write_landing_metadata,
)

_NC_WKT = (
    "POLYGON ((-79.1 35.5, -78.5 35.5, -78.5 36.0, -79.1 36.0, -79.1 35.5))"
)


def _product_profile() -> dict:
    """Build a Product landing-page fixture."""
    return {
        "referenceId": 663485,
        "referenceType": "Unpublished Report",
        "visibility": "Public",
        "fileAccess": "Public",
        "citation": "Britzke. 2007. Mammal inventory. https://doi.org/10.36967/663485",
        "bibliography": {
            "title": "Mammal inventory of selected parks",
            "abstract": "<p>Bat surveys.</p>",
            "notes": "Protocol revision.",
            "issued": {"year": 2007, "precision": "YYYY"},
            "contacts": [
                {
                    "contactType": "Author(s)",
                    "contacts": [
                        {
                            "firstName": "Eric",
                            "primaryName": "Britzke",
                            "affiliation": "USACE",
                        }
                    ],
                }
            ],
        },
        "units": [{"unitCode": "BLRI", "unitName": "Blue Ridge Parkway"}],
        "boundingBoxes": [{"wkt": _NC_WKT}],
        "filesAndLinks": [
            {
                "fileId": 147164,
                "resourceType": "Digital File",
                "url": "https://irma.nps.gov/DataStore/DownloadFile/147164",
                "fileName": "report.pdf",
            }
        ],
    }


class TestNpsLandingMetadata(unittest.TestCase):
    """Tests for product/project landing-page JSON."""

    def test_landing_metadata_dict_includes_units_and_contacts(self) -> None:
        """Product JSON captures landing-page people, notes, and geography."""
        payload = landing_metadata_dict(_product_profile())
        self.assertEqual(payload["reference_id"], 663485)
        self.assertEqual(payload["title"], "Mammal inventory of selected parks")
        self.assertIn("Authors", [item["role"] for item in payload["contacts"]])
        self.assertEqual(payload["notes"], "Protocol revision.")
        self.assertEqual(payload["units"][0]["code"], "BLRI")
        self.assertIn("North Carolina", payload["geographic_coverage"])
        self.assertEqual(payload["time_start"], "2007")
        self.assertIn("Bat surveys.", payload["summary"])
        self.assertEqual(payload["doi"], "10.36967/663485")
        self.assertIn("10.36967/663485", payload["summary"])
        self.assertEqual(payload["files"][0]["file_name"], "report.pdf")

    def test_write_landing_metadata_utf8_json(self) -> None:
        """Landing metadata is written as UTF-8 JSON."""
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "pkg" / PRODUCT_METADATA_NAME
            write_landing_metadata(dest, _product_profile())
            payload = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(payload["reference_id"], 663485)
            self.assertTrue(dest.is_file())


if __name__ == "__main__":
    unittest.main()
