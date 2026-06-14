"""Unit tests for UploadLargeFiles module."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from storage import Storage
from upload.UploadLargeFiles import (
    MAX_PROJECT_FILE_SIZE_BYTES,
    STATUS_FINISH_WAIT,
    STATUS_UPLOADED_EXPANDED,
    STATUS_UPLOADED_LARGE_FILE,
    UPLOAD_LARGE_FILES_TIMEOUT_MS,
    UploadLargeFiles,
    is_eligible_for_upload_large_files,
    planned_out_names,
    project_under_size_limit,
)
from utils.Args import Args
from utils.Logger import Logger


class TestUploadLargeFilesHelpers(unittest.TestCase):
    def test_upload_timeout_is_two_hours(self) -> None:
        self.assertEqual(UPLOAD_LARGE_FILES_TIMEOUT_MS, 2 * 60 * 60 * 1000)

    def test_project_under_size_limit(self) -> None:
        under = {"file_size": "10.0 GB"}
        at_limit = {"file_size": format_bytes(MAX_PROJECT_FILE_SIZE_BYTES)}
        over = {"file_size": format_bytes(MAX_PROJECT_FILE_SIZE_BYTES + 1)}
        missing = {"file_size": None}

        self.assertTrue(project_under_size_limit(under))
        self.assertFalse(project_under_size_limit(at_limit))
        self.assertFalse(project_under_size_limit(over))
        self.assertFalse(project_under_size_limit(missing))

    def test_is_eligible_for_upload_large_files(self) -> None:
        self.assertTrue(
            is_eligible_for_upload_large_files(
                {"status": STATUS_UPLOADED_LARGE_FILE, "file_size": "10.0 GB"}
            )
        )
        self.assertFalse(
            is_eligible_for_upload_large_files(
                {
                    "status": STATUS_UPLOADED_LARGE_FILE,
                    "file_size": format_bytes(MAX_PROJECT_FILE_SIZE_BYTES),
                }
            )
        )
        self.assertTrue(
            is_eligible_for_upload_large_files(
                {"status": STATUS_UPLOADED_EXPANDED, "file_size": "500.0 GB"}
            )
        )
        self.assertTrue(
            is_eligible_for_upload_large_files(
                {"status": STATUS_UPLOADED_EXPANDED, "file_size": None}
            )
        )

    def test_planned_out_names(self) -> None:
        lines = [
            'aria2c -c -x 16 -s 16 -j 1 --user-agent="UA" '
            '-d "C:\\data" -o "big.zip" "https://example.com/big.zip"',
            'aria2c -c -x 8 -s 8 -j 1 --user-agent="UA" '
            '-d "C:\\data" -o "other.zip" "https://example.com/other.zip"',
        ]
        self.assertEqual(planned_out_names(lines), ["big.zip", "other.zip"])


def format_bytes(n: int) -> str:
    from utils.file_utils import format_file_size

    return format_file_size(n)


class TestUploadLargeFilesRun(unittest.TestCase):
    def setUp(self) -> None:
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "upload_large_files"]
        Args._initialized = False
        Args._config = {}
        Args._parsed_args = {}
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_db_path = self.temp_dir / "test.db"
        self.storage = Storage.initialize("StorageSQLLite", db_path=self.test_db_path)
        self.module = UploadLargeFiles()

    def tearDown(self) -> None:
        sys.argv = self._original_argv
        self.storage.close()
        Storage.reset()
        Args._initialized = False
        if self.temp_dir.exists():
            import shutil

            shutil.rmtree(self.temp_dir)

    def test_run_project_not_found(self) -> None:
        with patch("upload.UploadIssueReporter.record_error") as mock_error:
            self.module.run(9999)
            mock_error.assert_called_once()
            self.assertIn("not found", mock_error.call_args[0][1])

    def test_run_rejects_over_size_limit(self) -> None:
        drpid = Storage.create_record("https://example.com/test")
        Storage.update_record(
            drpid,
            {
                "status": STATUS_UPLOADED_LARGE_FILE,
                "datalumos_id": "123",
                "file_size": format_bytes(MAX_PROJECT_FILE_SIZE_BYTES),
            },
        )
        with patch("upload.UploadIssueReporter.record_error") as mock_error:
            self.module.run(drpid)
            mock_error.assert_called()
            self.assertIn("25 GB", mock_error.call_args[0][1])

    @patch("upload.UploadLargeFiles.Storage")
    @patch("upload.UploadLargeFiles.ensure_aria2_cmd", return_value=(Path("x.cmd"), []))
    @patch("upload.UploadLargeFiles.large_files_on_disk", return_value=["big.zip"])
    @patch.object(UploadLargeFiles, "_upload_files_to_existing_project")
    def test_run_uploads_on_disk_files_and_sets_finish_wait(
        self,
        mock_upload: MagicMock,
        mock_on_disk: MagicMock,
        mock_ensure_cmd: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        folder = self.temp_dir / "data"
        folder.mkdir()
        (folder / "big.zip").write_bytes(b"x" * 10)

        mock_storage.get.return_value = {
            "status": STATUS_UPLOADED_LARGE_FILE,
            "datalumos_id": "999",
            "folder_path": str(folder),
            "file_size": "5.0 GB",
        }
        uploader = UploadLargeFiles()
        uploader._session = MagicMock()
        uploader.run(7)

        mock_upload.assert_called_once()
        file_paths = mock_upload.call_args[0][2]
        self.assertEqual([p.name for p in file_paths], ["big.zip"])
        mock_storage.update_record.assert_called_with(7, {"status": STATUS_FINISH_WAIT})


if __name__ == "__main__":
    unittest.main()
