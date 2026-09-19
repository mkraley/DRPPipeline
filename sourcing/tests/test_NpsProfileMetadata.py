"""Tests for IRMA Profile summary, contacts, and temporal mapping."""

from __future__ import annotations

import unittest

from sourcing.NpsProfileMetadata import (
    AGENCY,
    OFFICE,
    irma_date,
    merge_doi_notes,
    profile_dois,
    profile_summary_html,
    profile_temporal_fields,
)


class TestNpsProfileMetadata(unittest.TestCase):
    """Tests for landing-page summary and date pairing."""

    def test_agency_and_office_constants(self) -> None:
        """DataLumos agency/office are DOI and NPS."""
        self.assertEqual(AGENCY, "Department of the Interior")
        self.assertEqual(OFFICE, "National Park Service")

    def test_irma_date_keeps_year_precision(self) -> None:
        """YYYY precision stays year-only even when yyyymmdd is January 1."""
        self.assertEqual(
            irma_date({"year": 2013, "precision": "YYYY", "yyyymmdd": "2013-01-01"}),
            "2013",
        )

    def test_irma_date_normalizes_full_stamp(self) -> None:
        """Full-precision IRMA stamps become ISO dates."""
        self.assertEqual(
            irma_date({"precision": "YYYYMMDD", "yyyymmdd": "20070615"}),
            "2007-06-15",
        )

    def test_temporal_fields_pair_start_only(self) -> None:
        """A Project Start Date without an end date is paired to both bounds."""
        profile = {
            "bibliography": {
                "contentBegin": {"year": 2013, "precision": "YYYY"},
            }
        }
        self.assertEqual(
            profile_temporal_fields(profile),
            {"time_start": "2013", "time_end": "2013"},
        )

    def test_temporal_fields_fall_back_to_issued(self) -> None:
        """Issued date is used when contentBegin/contentEnd are missing."""
        profile = {"bibliography": {"issued": {"year": 2007, "precision": "YYYY"}}}
        self.assertEqual(
            profile_temporal_fields(profile),
            {"time_start": "2007", "time_end": "2007"},
        )

    def test_summary_includes_doi_from_citation(self) -> None:
        """DOIs in IRMA citations become a labeled summary field."""
        profile = {
            "citation": (
                "Hughes J. 2018. Protocol. National Park Service. "
                "https://doi.org/10.36967/2258269"
            ),
            "bibliography": {"abstract": "<p>Protocol narrative.</p>"},
        }
        summary = profile_summary_html(profile)
        self.assertIn("10.36967/2258269", summary)
        self.assertIn("DOI", summary)

    def test_profile_dois_ignores_orcid_and_dedupes(self) -> None:
        """ORCID URLs are not treated as DOIs; duplicate DOIs are stored once."""
        profile = {
            "citation": (
                '<a href="https://orcid.org/0000-0003-4438-7094">x</a> '
                "https://doi.org/10.57830/2308545. https://doi.org/10.57830/2308545"
            )
        }
        self.assertEqual(profile_dois(profile), ["10.57830/2308545"])
        notes = merge_doi_notes("Collection 9688: IMD", ["10.57830/2308545"])
        self.assertIn("DOI: 10.57830/2308545", notes)
        self.assertIn("Collection 9688: IMD", notes)

    def test_summary_includes_landing_fields_not_hierarchy(self) -> None:
        """Summary captures leads, publisher, and notes without a breadcrumb."""
        profile = {
            "citation": "NPS. 2013. Report.",
            "bibliography": {
                "abstract": "<p>Counts of galax.</p>",
                "publisher": {"publisherName": "National Park Service"},
                "notes": "See protocol.",
                "contacts": [
                    {
                        "contactType": "Sponsor(s)",
                        "contacts": [{"firstName": "IMD", "primaryName": "Network"}],
                    }
                ],
            },
        }
        summary = profile_summary_html(profile)
        self.assertIn("Counts of galax.", summary)
        self.assertIn("Sponsors", summary)
        self.assertIn("IMD Network", summary)
        self.assertIn("Publisher", summary)
        self.assertIn("National Park Service", summary)
        self.assertIn("Notes", summary)
        self.assertNotIn("Collection ", summary)


if __name__ == "__main__":
    unittest.main()
