"""Unit tests for structured project error text."""

import unittest
from unittest.mock import patch

from utils.ErrorRecord import error_summary, executing_module, format_project_error


class TestErrorSummary(unittest.TestCase):
    """Test error_summary."""

    def test_uses_the_detail_after_a_generic_failure(self) -> None:
        message = "Download failed: report.csv - https://example.com/a"
        self.assertEqual(
            error_summary(message),
            "report.csv - https://example.com/a",
        )

    def test_drops_exception_wrapper_and_drpid(self) -> None:
        message = "Exception during collection for DRPID 12: Timeout reading page"
        self.assertEqual(error_summary(message), "Timeout reading page")

    def test_drops_orchestrator_wrapper(self) -> None:
        message = "Orchestrator module='collect' DRPID=12 exception: TimeoutError"
        self.assertEqual(error_summary(message), "TimeoutError")

    def test_drops_an_id_only_clause(self) -> None:
        self.assertEqual(
            error_summary("Missing folder_path for DRPID 12"),
            "Missing folder_path",
        )
        self.assertEqual(
            error_summary("DRPID 12: missing source_url in database"),
            "missing source_url in database",
        )

    def test_keeps_a_specific_message_without_a_generic_prefix(self) -> None:
        self.assertEqual(
            error_summary("Failed to create output folder"),
            "Failed to create output folder",
        )
        self.assertEqual(
            error_summary("Not an IRMA Profile URL: https://example.com/x"),
            "Not an IRMA Profile URL: https://example.com/x",
        )

    def test_flattens_newlines(self) -> None:
        self.assertEqual(error_summary("line one\nline two"), "line one line two")


class TestFormatProjectError(unittest.TestCase):
    """Test format_project_error."""

    def test_summary_is_unlabeled_and_other_fields_are_labeled(self) -> None:
        text = format_project_error(
            "Download failed: report.csv - https://example.com/a",
            12,
            "34567",
            "collect",
            "2026-10-04 17:49:00",
        )
        self.assertEqual(
            text,
            "\n".join(
                [
                    "report.csv - https://example.com/a",
                    "drpid: 12",
                    "datalumos_id: 34567",
                    "timestamp: 2026-10-04 17:49:00",
                    "module: collect",
                    "details: Download failed: report.csv - https://example.com/a",
                ]
            ),
        )
        self.assertNotIn("description:", text)

    def test_empty_datalumos_id_keeps_the_name(self) -> None:
        text = format_project_error("boom", 3, None, "upload", "2026-10-04 17:49:00")
        self.assertIn("\ndatalumos_id:\n", "\n" + text + "\n")

    def test_details_stay_on_one_line(self) -> None:
        text = format_project_error(
            "Publish failed:\nprofile missing",
            1,
            "",
            "publish",
            "2026-10-04 17:49:00",
        )
        self.assertTrue(text.startswith("profile missing\n"))
        details = [line for line in text.splitlines() if line.startswith("details:")]
        self.assertEqual(details, ["details: Publish failed: profile missing"])


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
