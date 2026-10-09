"""Tests for resume_download aria2 failure reporting."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from storage.ProjectFileStore import ProjectFileRow
from upload.ResumeDownload import _fetch_row
from upload.UploadIssueReporter import UploadIssueReporter
from utils.Logger import Logger


class TestResumeDownload(unittest.TestCase):
    """Aria2 console errors are stored on the project."""

    def setUp(self) -> None:
        """Initialize logging for record_error."""
        Logger.initialize(log_level="WARNING")

    def test_aria2_console_error_is_recorded(self) -> None:
        """A failed aria2 run records the console error on the project."""
        import collectors.UsfsAria2Export as aria2_export

        row = ProjectFileRow(
            drpid=29,
            relative_path="folder/file.pdf",
            size_bytes=10,
            source_url="https://irma.nps.gov/DataStore/DownloadFile/1",
            downloaded=False,
            uploaded=False,
        )
        aria2_export._last_console_error = (
            "[ERROR] Exception caught Failed to write into the segment file"
        )
        reporter = UploadIssueReporter(29)
        store = MagicMock()
        with tempfile.TemporaryDirectory() as folder:
            with patch("upload.ResumeDownload.run_aria2_downloads", return_value=(0, 1)):
                with patch("upload.UploadIssueReporter.record_error") as record_error:
                    ok = _fetch_row(29, Path(folder), row, store, reporter, Path(folder))
        self.assertFalse(ok)
        store.mark_downloaded.assert_not_called()
        message = record_error.call_args[0][1]
        self.assertIn("Download failed: folder/file.pdf", message)
        self.assertIn("Failed to write into the segment file", message)


if __name__ == "__main__":
    unittest.main()
