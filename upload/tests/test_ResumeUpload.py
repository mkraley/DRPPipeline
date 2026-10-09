"""Unit tests for ResumeUpload."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from storage.ProjectFileStore import ProjectFileRow
from upload.ResumeUpload import ResumeUpload
from utils.Errors import ProjectAbort
from utils.Logger import Logger


def _row(relative_path: str) -> ProjectFileRow:
    """Build a downloaded, not-yet-uploaded file row."""
    return ProjectFileRow(
        drpid=12,
        relative_path=relative_path,
        size_bytes=10,
        source_url="https://irma.nps.gov/DataStore/DownloadFile/1",
        downloaded=True,
        uploaded=False,
    )


class TestResumeUpload(unittest.TestCase):
    """Pending files from every product folder go up in one zip."""

    def setUp(self) -> None:
        """Quiet the logger."""
        Logger.initialize(log_level="WARNING")

    @patch("upload.DataLumosAuthenticator.wait_for_human_verification")
    @patch("upload.DataLumosFileUploader.DataLumosFileUploader")
    @patch("upload.ResumeUpload.ProjectFileStore.from_storage")
    def test_pending_files_upload_in_one_batch(
        self,
        mock_store_factory: MagicMock,
        mock_uploader_cls: MagicMock,
        _mock_wait: MagicMock,
    ) -> None:
        """Files in different product folders are passed to one upload call."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "Product_A" / "a.pdf"
            second = root / "Product_B" / "b.pdf"
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_bytes(b"a")
            second.write_bytes(b"b")
            store = MagicMock()
            store.list_pending_uploads.return_value = [
                _row("Product_A/a.pdf"),
                _row("Product_B/b.pdf"),
            ]
            mock_store_factory.return_value = store
            uploader = mock_uploader_cls.return_value
            resume = ResumeUpload()
            page = MagicMock()
            resume._session.ensure_browser = MagicMock(return_value=page)
            resume._session.ensure_authenticated = MagicMock()

            resume._upload_pending(12, {"datalumos_id": "255551"}, root, MagicMock())

            uploader.upload_paths_preserving_folders.assert_called_once_with(
                root, [first, second]
            )
            store.mark_uploaded.assert_called_once_with(
                12, ["Product_A/a.pdf", "Product_B/b.pdf"]
            )

    def test_missing_pending_file_stops_before_upload(self) -> None:
        """A missing catalog file is reported and not uploaded."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reporter = MagicMock()
            resume = ResumeUpload()
            with self.assertRaises(ProjectAbort):
                resume._pending_paths(root, [_row("Product_A/missing.pdf")], reporter)
            reporter.error.assert_called_once()
