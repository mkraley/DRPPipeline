"""Tests for GlobusSurveyNotes."""

from __future__ import annotations

import unittest

from collectors.GlobusPathInventory import GlobusInventorySummary
from collectors.GlobusSurveyNotes import (
    format_survey_line,
    has_survey_notes,
    upsert_survey_line,
)


class TestGlobusSurveyNotes(unittest.TestCase):
    """Tests for status_notes inventory formatting."""

    def _summary(self) -> GlobusInventorySummary:
        """Build a sample inventory summary."""
        return GlobusInventorySummary(
            endpoint_id="src-ep",
            root_path="/node29313/",
            file_count=12,
            dir_count=3,
            total_bytes=50_000_000_000,
        )

    def test_format_survey_line(self) -> None:
        """Survey line includes counts, size, and date."""
        line = format_survey_line(self._summary(), survey_date="2026-06-29")
        self.assertIn("Globus remote inventory:", line)
        self.assertIn("12 files", line)
        self.assertIn("3 dirs", line)
        self.assertIn("46.6 GB", line)
        self.assertIn("surveyed 2026-06-29", line)

    def test_upsert_replaces_existing_line(self) -> None:
        """Existing inventory line is replaced on re-survey."""
        notes = (
            "External data URL: https://app.globus.org/file-manager?x=1\n"
            "Globus remote inventory: old line"
        )
        updated = upsert_survey_line(notes, self._summary(), survey_date="2026-06-29")
        self.assertIn("External data URL:", updated)
        self.assertNotIn("old line", updated)
        self.assertTrue(has_survey_notes(updated))


if __name__ == "__main__":
    unittest.main()
