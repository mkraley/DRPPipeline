"""Unit tests for trial metadata prepared from a Storage row."""

from __future__ import annotations

import unittest

from upload.DepositMetadata import metadata_from_project, trial_metadata_from_project


class TestDepositMetadata(unittest.TestCase):
    """Title prefix and the same field cleanup the uploader applies."""

    def test_production_title_is_not_prefixed(self) -> None:
        """Production deposits use the prepared title with no trial marker."""
        metadata = metadata_from_project({"title": "River gauges", "summary": "A set."})
        self.assertNotIn("TRIAL", metadata.title)
        self.assertIn("River gauges", metadata.title)

    def test_title_is_prefixed_with_trial(self) -> None:
        """The DataLumos title is marked so the deposit can be deleted later."""
        metadata = trial_metadata_from_project({"title": "River gauges", "summary": "A set."})
        self.assertTrue(metadata.title.startswith("TRIAL "))
        self.assertIn("River gauges", metadata.title)

    def test_cdc_short_name_is_expanded(self) -> None:
        """CDC is expanded the same way the form filler expands it."""
        metadata = trial_metadata_from_project(
            {"title": "Survey", "summary": "Text", "agency": "CDC", "office": "CDC"}
        )
        self.assertEqual(len(metadata.agencies), 1)
        self.assertIn("Centers for Disease Control", metadata.agencies[0])

    def test_short_keywords_are_dropped(self) -> None:
        """Tokens of two characters or fewer are not sent as subject terms."""
        metadata = trial_metadata_from_project(
            {"title": "Survey", "summary": "Text", "keywords": "US, health, air"}
        )
        self.assertEqual(metadata.keywords, ("health", "air"))

    def test_notes_include_download_date(self) -> None:
        """The download date is appended the way the form filler appends it."""
        metadata = trial_metadata_from_project(
            {
                "title": "Survey",
                "summary": "Text",
                "collection_notes": "Collected by the office.",
                "download_date": "2026-01-02",
            }
        )
        self.assertIn("(Downloaded 2026-01-02)", metadata.notes)


if __name__ == "__main__":
    unittest.main()
