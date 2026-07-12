"""
Unit tests for UploadVerifier.
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

from utils.Args import Args
from utils.Logger import Logger

from verify.DatalumosViewFileStats import DatalumosViewFileStats
from verify.UploadVerifier import UploadVerifier


class TestUploadVerifier(unittest.TestCase):
    """Tests for UploadVerifier module."""

    def setUp(self) -> None:
        """Reset verifier state before each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "verify_upload"]
        Args.initialize()
        Logger.initialize(log_level="ERROR", log_file=False)
        UploadVerifier._sheet_index = None

    def tearDown(self) -> None:
        """Restore argv after each test."""
        sys.argv = self._original_argv
        UploadVerifier._sheet_index = None

    @patch("verify.UploadVerifier.Logger")
    @patch("verify.UploadVerifier.Storage")
    def test_run_missing_project_logs_error(
        self, mock_storage: MagicMock, mock_logger: MagicMock
    ) -> None:
        """Test missing project logs an error."""
        mock_storage.get.return_value = None
        verifier = UploadVerifier()
        verifier.run(1)
        mock_logger.error.assert_called_once()
        self.assertIn("not found", mock_logger.error.call_args[0][0])

    @patch("verify.UploadVerifier.Logger")
    @patch("verify.UploadVerifier.Storage")
    def test_run_missing_sheet_row_logs_error(
        self, mock_storage: MagicMock, mock_logger: MagicMock
    ) -> None:
        """Test missing inventory sheet row logs an error."""
        mock_storage.get.return_value = {
            "DRPID": 1,
            "source_url": "https://example.gov/data",
            "num_files": 1,
            "file_size": "1000",
        }
        UploadVerifier._sheet_index = {}
        verifier = UploadVerifier()
        verifier.run(1)
        mock_logger.error.assert_called_once()
        self.assertIn("not found on inventory sheet", mock_logger.error.call_args[0][0])

    @patch("verify.UploadVerifier.Logger")
    @patch("verify.UploadVerifier.Storage")
    def test_run_missing_download_location_logs_error(
        self, mock_storage: MagicMock, mock_logger: MagicMock
    ) -> None:
        """Test empty Download Location logs an error."""
        mock_storage.get.return_value = {
            "DRPID": 1,
            "source_url": "https://example.gov/data",
            "num_files": 1,
            "file_size": "1000",
        }
        UploadVerifier._sheet_index = {
            "https://example.gov/data": {"URL": "https://example.gov/data"}
        }
        verifier = UploadVerifier()
        verifier.run(1)
        mock_logger.error.assert_called_once()
        self.assertIn("Download Location empty", mock_logger.error.call_args[0][0])

    @patch("verify.UploadVerifier.Logger")
    @patch("verify.UploadVerifier.Storage")
    def test_run_mismatch_logs_error(
        self, mock_storage: MagicMock, mock_logger: MagicMock
    ) -> None:
        """Test inventory mismatch logs verification errors when repair is skipped."""
        mock_storage.get.return_value = {
            "DRPID": 5,
            "source_url": "https://example.gov/data",
            "datalumos_id": "248712",
            "num_files": 2,
            "file_size": "2048",
        }
        UploadVerifier._sheet_index = {
            "https://example.gov/data": {
                "URL": "https://example.gov/data",
                "Download Location": "https://www.datalumos.org/datalumos/project/1/version/V1/view",
            }
        }
        verifier = UploadVerifier()
        verifier._fetch_page_stats = MagicMock(  # type: ignore[method-assign]
            return_value=DatalumosViewFileStats(
                file_count=1,
                total_bytes=2048,
                file_names=("a.txt",),
            )
        )
        verifier._try_repair_missing_files = MagicMock(  # type: ignore[method-assign]
            return_value=False
        )
        verifier.run(5)
        mock_logger.error.assert_called_once()
        message = mock_logger.error.call_args[0][0]
        self.assertIn("file count mismatch", message)
        self.assertIn("datalumos_id=248712", message)

    @patch("verify.UploadVerifier.MissingFileRepair")
    @patch("verify.UploadVerifier.Logger")
    @patch("verify.UploadVerifier.Storage")
    def test_run_repairs_missing_files_and_sets_reuploaded(
        self,
        mock_storage: MagicMock,
        mock_logger: MagicMock,
        mock_repair_cls: MagicMock,
    ) -> None:
        """When DL count is low, successful repair sets status re-uploaded."""
        mock_storage.get.return_value = {
            "DRPID": 5,
            "source_url": "https://example.gov/data",
            "datalumos_id": "248712",
            "num_files": 2,
            "file_size": "2048",
            "folder_path": r"C:\data\DRP000005",
        }
        UploadVerifier._sheet_index = {
            "https://example.gov/data": {
                "URL": "https://example.gov/data",
                "Download Location": "https://www.datalumos.org/datalumos/project/1/version/V1/view",
            }
        }
        mock_repair_cls.return_value.repair.return_value = True
        verifier = UploadVerifier()
        verifier._fetch_page_stats = MagicMock(  # type: ignore[method-assign]
            return_value=DatalumosViewFileStats(
                file_count=1,
                total_bytes=100,
                file_names=("keep.pdf",),
            )
        )
        verifier.run(5)
        mock_storage.update_record.assert_called_once_with(
            5, {"status": "re-uploaded"}
        )
        mock_logger.error.assert_not_called()
        info_msg = mock_logger.info.call_args[0][0]
        self.assertIn("re-uploaded", info_msg)

    @patch("verify.UploadVerifier.Logger")
    @patch("verify.UploadVerifier.Storage")
    def test_run_size_only_mismatch_does_not_repair(
        self, mock_storage: MagicMock, mock_logger: MagicMock
    ) -> None:
        """Size-only mismatches are logged without attempting repair."""
        mock_storage.get.return_value = {
            "DRPID": 5,
            "source_url": "https://example.gov/data",
            "datalumos_id": "248712",
            "num_files": 1,
            "file_size": "1000",
        }
        UploadVerifier._sheet_index = {
            "https://example.gov/data": {
                "URL": "https://example.gov/data",
                "Download Location": "https://www.datalumos.org/datalumos/project/1/version/V1/view",
            }
        }
        verifier = UploadVerifier()
        verifier._fetch_page_stats = MagicMock(  # type: ignore[method-assign]
            return_value=DatalumosViewFileStats(
                file_count=1,
                total_bytes=5000,
                file_names=("a.zip",),
            )
        )
        verifier._try_repair_missing_files = MagicMock(  # type: ignore[method-assign]
            return_value=False
        )
        verifier.run(5)
        verifier._try_repair_missing_files.assert_not_called()
        mock_logger.error.assert_called()
        self.assertIn("file size mismatch", mock_logger.error.call_args[0][0])

    @patch("verify.UploadVerifier.set_records_per_page")
    @patch("verify.UploadVerifier.DatalumosViewFileStats.from_page")
    def test_fetch_page_stats_sets_records_per_page(
        self,
        mock_from_page: MagicMock,
        mock_set_records: MagicMock,
    ) -> None:
        """_fetch_page_stats expands Records per page before extracting files."""
        mock_from_page.return_value = DatalumosViewFileStats(
            file_count=1, total_bytes=100
        )
        verifier = UploadVerifier()
        page = MagicMock()
        response = MagicMock()
        response.status = 200
        page.goto.return_value = response
        verifier._session = MagicMock()
        verifier._session.ensure_browser.return_value = page

        with patch(
            "upload.DataLumosAuthenticator.wait_for_human_verification"
        ):
            stats = verifier._fetch_page_stats(
                "https://www.datalumos.org/datalumos/project/1/version/V1/view"
            )

        mock_set_records.assert_called_once_with(page)
        mock_from_page.assert_called_once_with(page)
        self.assertEqual(stats.file_count, 1)

    @patch("verify.UploadVerifier.Logger")
    @patch("verify.UploadVerifier.Storage")
    def test_run_match_logs_success_summary(
        self, mock_storage: MagicMock, mock_logger: MagicMock
    ) -> None:
        """Test successful verification logs expected/actual files and size."""
        mock_storage.get.return_value = {
            "DRPID": 5,
            "source_url": "https://example.gov/data",
            "num_files": 1,
            "file_size": "2048",
        }
        UploadVerifier._sheet_index = {
            "https://example.gov/data": {
                "URL": "https://example.gov/data",
                "Download Location": "https://www.datalumos.org/datalumos/project/1/version/V1/view",
            }
        }
        verifier = UploadVerifier()
        verifier._fetch_page_stats = MagicMock(  # type: ignore[method-assign]
            return_value=DatalumosViewFileStats(file_count=1, total_bytes=2048)
        )
        verifier.run(5)
        mock_logger.error.assert_not_called()
        mock_logger.info.assert_called_once()
        message = mock_logger.info.call_args[0][0]
        self.assertIn("DRPID 5: OK", message)
        self.assertIn("files 1/1", message)
        self.assertIn("size 2048/", message)


if __name__ == "__main__":
    unittest.main()
