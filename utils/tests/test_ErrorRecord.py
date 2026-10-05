"""Unit tests for structured project error text."""

import unittest
from unittest.mock import patch

from utils.ErrorRecord import (
    brief_error_description,
    executing_module,
    format_project_error,
)


class TestBriefErrorDescription(unittest.TestCase):
    """Test brief_error_description."""

    def test_uses_text_before_colon_when_short(self) -> None:
        message = "Download failed: report.csv - https://example.com/a"
        self.assertEqual(brief_error_description(message), "Download failed")

    def test_keeps_full_message_without_colon(self) -> None:
        self.assertEqual(
            brief_error_description("Failed to create output folder"),
            "Failed to create output folder",
        )

    def test_flattens_newlines(self) -> None:
        self.assertEqual(brief_error_description("line one\nline two"), "line one line two")


class TestFormatProjectError(unittest.TestCase):
    """Test format_project_error."""

    def test_one_field_per_line(self) -> None:
        text = format_project_error(
            "Download failed: report.csv",
            12,
            "34567",
            "collect",
            "2026-10-04 17:49:00",
        )
        self.assertEqual(
            text,
            "\n".join(
                [
                    "description: Download failed",
                    "drpid: 12",
                    "datalumos_id: 34567",
                    "timestamp: 2026-10-04 17:49:00",
                    "module: collect",
                    "details: Download failed: report.csv",
                ]
            ),
        )

    def test_empty_datalumos_id_keeps_the_name(self) -> None:
        text = format_project_error("boom", 3, None, "upload", "2026-10-04 17:49:00")
        self.assertIn("\ndatalumos_id:\n", "\n" + text + "\n")

    def test_details_stay_on_one_line(self) -> None:
        text = format_project_error(
            "Publish failed:\ntraceback line",
            1,
            "",
            "publish",
            "2026-10-04 17:49:00",
        )
        details = [line for line in text.splitlines() if line.startswith("details:")]
        self.assertEqual(details, ["details: Publish failed: traceback line"])


class TestExecutingModule(unittest.TestCase):
    """Test executing_module."""

    def test_explicit_name_wins(self) -> None:
        self.assertEqual(executing_module("resume_download"), "resume_download")

    def test_uses_args_module_when_set(self) -> None:
        with patch("utils.ErrorRecord._configured_module", return_value="collect"):
            self.assertEqual(executing_module(), "collect")

    def test_falls_back_to_caller_file(self) -> None:
        with patch("utils.ErrorRecord._configured_module", return_value=None):
            self.assertEqual(executing_module(), "test_ErrorRecord.py")
