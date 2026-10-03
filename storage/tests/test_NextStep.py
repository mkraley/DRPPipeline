"""Tests for next_step_for_status."""

import unittest

from storage.NextStep import next_step_for_status


class TestNextStep(unittest.TestCase):
    """Status to next-module mapping."""

    def test_known_modules(self) -> None:
        """Common statuses map to one module."""
        self.assertEqual(next_step_for_status("sourced"), "collect")
        self.assertEqual(next_step_for_status("collected"), "upload")
        self.assertEqual(next_step_for_status("collected - large file"), "upload")
        self.assertEqual(next_step_for_status("uploaded"), "publish")
        self.assertEqual(
            next_step_for_status("uploaded - large file"), "upload_large_files"
        )
        self.assertEqual(next_step_for_status("re-uploaded"), "republish")
        self.assertEqual(next_step_for_status("updated_inventory"), "verify_upload")
        self.assertEqual(next_step_for_status("not_found"), "publish")
        self.assertEqual(
            next_step_for_status("collector_hold - needs login"), "publish"
        )

    def test_error_status_uses_the_base_status(self) -> None:
        """A compact error status retries the module for the status it came from."""
        self.assertEqual(next_step_for_status("sourced-error"), "collect")
        self.assertEqual(
            next_step_for_status("uploaded-large-file-error"), "upload_large_files"
        )

    def test_terminal_statuses_have_no_next_module(self) -> None:
        """Finished rows do not name another module."""
        self.assertIsNone(next_step_for_status("dupe_in_DL"))
        self.assertIsNone(next_step_for_status("updated_not_found"))
        self.assertIsNone(next_step_for_status("updated_collector_hold"))

    def test_unsure_statuses_are_question_marks(self) -> None:
        """Manual gates and unknown statuses are '?'."""
        self.assertEqual(next_step_for_status(None), "?")
        self.assertEqual(next_step_for_status(""), "?")
        self.assertEqual(next_step_for_status("finish wait"), "uploaded")
        self.assertEqual(next_step_for_status("collected - large"), "upload")
        self.assertEqual(next_step_for_status("collected - xlarge"), "upload")
        self.assertEqual(next_step_for_status("uploaded - large"), "resume_download")
        self.assertEqual(next_step_for_status("uploaded - xlarge"), "resize wait")
        self.assertEqual(next_step_for_status("resize wait"), "resized")
        self.assertEqual(next_step_for_status("resized"), "resume_download")
        self.assertEqual(next_step_for_status("downloaded"), "resume_upload")
        self.assertEqual(next_step_for_status("uploaded-large-error"), "resume_download")
        self.assertEqual(next_step_for_status("resized-error"), "resume_download")
        self.assertEqual(next_step_for_status("collected - file pending"), "?")
        self.assertEqual(next_step_for_status("error"), "?")
        self.assertEqual(next_step_for_status("something-new"), "?")

    def test_globus_external_archive(self) -> None:
        """Globus notes select collect_adc_globus; other archives stay unsure."""
        notes = "https://app.globus.org/file-manager?origin_id=abc&origin_path=%2Fdata%2F"
        self.assertEqual(
            next_step_for_status("collected - external archive", notes),
            "collect_adc_globus",
        )
        self.assertEqual(
            next_step_for_status("collected - external archive", "https://example.com"),
            "?",
        )


if __name__ == "__main__":
    unittest.main()
