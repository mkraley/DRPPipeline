"""
Unit tests for DataLumosFileUploader.
"""

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

from utils.Logger import Logger

from upload.DataLumosFileUploader import (
    FILE_PER_FILE_QUEUE_PHRASES,
    FILE_UPLOAD_ACCEPTANCE_PHRASES,
    DataLumosFileUploader,
)


class TestDataLumosFileUploader(unittest.TestCase):
    """Test cases for DataLumosFileUploader."""

    @classmethod
    def setUpClass(cls) -> None:
        """Initialize Logger once for all tests."""
        Logger.initialize(log_level="WARNING")

    def test_init(self) -> None:
        """Test file uploader initialization."""
        mock_page = MagicMock()
        uploader = DataLumosFileUploader(mock_page, timeout=5000)
        self.assertEqual(uploader._page, mock_page)
        self.assertEqual(uploader._timeout, 5000)

    def test_get_file_paths_returns_files(self) -> None:
        """Test get_file_paths returns only files, not subdirs."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.txt").write_text("a")
            (Path(tmp) / "b.csv").write_text("b")
            Path(tmp).joinpath("sub").mkdir()
            (Path(tmp) / "sub" / "c.txt").write_text("c")
            mock_page = MagicMock()
            uploader = DataLumosFileUploader(mock_page)
            paths = uploader.get_file_paths(tmp)
            names = {p.name for p in paths}
            self.assertEqual(names, {"a.txt", "b.csv"})

    def test_get_file_paths_empty_folder(self) -> None:
        """Test get_file_paths returns empty list for empty folder."""
        with tempfile.TemporaryDirectory() as tmp:
            mock_page = MagicMock()
            uploader = DataLumosFileUploader(mock_page)
            paths = uploader.get_file_paths(tmp)
            self.assertEqual(paths, [])

    def test_count_upload_batches_flat_folder(self) -> None:
        """Flat folder: batch count equals number of top-level files."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.txt").write_text("a")
            (Path(tmp) / "b.txt").write_text("b")
            uploader = DataLumosFileUploader(MagicMock())
            self.assertEqual(uploader.count_upload_batches(tmp), 2)

    def test_count_upload_batches_zip_when_subfolder(self) -> None:
        """Subfolder present: single zip upload counts as 1 batch."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.txt").write_text("a")
            (Path(tmp) / "sub").mkdir()
            (Path(tmp) / "sub" / "b.txt").write_text("b")
            uploader = DataLumosFileUploader(MagicMock())
            self.assertEqual(uploader.count_upload_batches(tmp), 1)

    def test_upload_files_empty_folder_returns_without_error(self) -> None:
        """Test upload_files with empty folder returns without opening modal or raising."""
        with tempfile.TemporaryDirectory() as tmp:
            mock_page = MagicMock()
            uploader = DataLumosFileUploader(mock_page)
            uploader.upload_files(tmp)
            mock_page.locator.assert_not_called()

    def test_get_file_paths_missing_folder_raises(self) -> None:
        """Test get_file_paths raises FileNotFoundError for missing path."""
        mock_page = MagicMock()
        uploader = DataLumosFileUploader(mock_page)
        with self.assertRaises(FileNotFoundError):
            uploader.get_file_paths("/nonexistent/folder")

    def test_get_file_paths_not_directory_raises(self) -> None:
        """Test get_file_paths raises NotADirectoryError for file path."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = f.name
        try:
            mock_page = MagicMock()
            uploader = DataLumosFileUploader(mock_page)
            with self.assertRaises(NotADirectoryError):
                uploader.get_file_paths(path)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_folder_has_subfolders_true_when_subdir_exists(self) -> None:
        """Test _folder_has_subfolders returns True when folder has subdirs."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "sub").mkdir()
            mock_page = MagicMock()
            uploader = DataLumosFileUploader(mock_page)
            self.assertTrue(uploader._folder_has_subfolders(tmp))

    def test_folder_has_subfolders_false_when_only_files(self) -> None:
        """Test _folder_has_subfolders returns False when folder has only files."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.txt").write_text("a")
            mock_page = MagicMock()
            uploader = DataLumosFileUploader(mock_page)
            self.assertFalse(uploader._folder_has_subfolders(tmp))

    def test_folder_has_subfolders_false_when_empty(self) -> None:
        """Test _folder_has_subfolders returns False for empty folder."""
        with tempfile.TemporaryDirectory() as tmp:
            mock_page = MagicMock()
            uploader = DataLumosFileUploader(mock_page)
            self.assertFalse(uploader._folder_has_subfolders(tmp))

    def test_zip_folder_contents_creates_valid_zip_with_files_and_subdirs(self) -> None:
        """Test _zip_folder_contents creates a zip containing all contents."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "root.txt").write_text("root")
            sub = Path(tmp) / "sub"
            sub.mkdir()
            (sub / "nested.txt").write_text("nested")
            mock_page = MagicMock()
            uploader = DataLumosFileUploader(mock_page)
            zip_path = uploader._zip_folder_contents(tmp)
            try:
                self.assertTrue(zip_path.exists())
                with zipfile.ZipFile(zip_path, "r") as zf:
                    names = set(zf.namelist())
                self.assertIn("root.txt", names)
                self.assertIn("sub/nested.txt", names)
            finally:
                zip_path.unlink(missing_ok=True)

    def test_upload_files_with_subfolders_uses_import_from_zip(self) -> None:
        """Test upload_files with subfolders clicks Import From Zip, not Upload Files."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "sub").mkdir()
            (Path(tmp) / "sub" / "f.txt").write_text("x")

            def locator_side_effect(selector: str) -> MagicMock:
                loc = MagicMock()
                if selector == "#busy":
                    loc.count.return_value = 0
                else:
                    loc.wait_for = MagicMock()
                    loc.click = MagicMock()
                    loc.nth = MagicMock(return_value=MagicMock())
                    gbt = MagicMock()
                    gbt.count.return_value = 1
                    loc.get_by_text = MagicMock(return_value=gbt)
                    loc.inner_text = MagicMock(return_value="")
                return loc

            mock_page = MagicMock()
            mock_page.locator.side_effect = locator_side_effect
            mock_page.evaluate.return_value = "pw-datalumos-file-input"

            uploader = DataLumosFileUploader(mock_page)
            uploader.upload_files(tmp)

            calls = [c[0][0] for c in mock_page.locator.call_args_list]
            import_zip_calls = [c for c in calls if "Import From Zip" in c]
            upload_calls = [c for c in calls if "btn-primary" in str(c)]
            self.assertGreater(len(import_zip_calls), 0, "Should use Import From Zip")
            self.assertEqual(len(upload_calls), 0, "Should not use Upload Files")

    def test_phrase_occurrence_count_matches_processing_message(self) -> None:
        uploader = DataLumosFileUploader(MagicMock())
        text = "Uploaded files are being processed..."
        n = uploader._phrase_occurrence_count(text, FILE_UPLOAD_ACCEPTANCE_PHRASES)
        self.assertGreaterEqual(n, 1)

    def test_has_batch_upload_status(self) -> None:
        uploader = DataLumosFileUploader(MagicMock())
        with unittest.mock.patch.object(
            uploader,
            "_modal_status_text",
            return_value="Uploaded files are being processed...",
        ):
            self.assertTrue(uploader._has_batch_upload_status(use_zip=False))

    def test_wait_until_queued_count_accepts_batch_processing_message(self) -> None:
        uploader = DataLumosFileUploader(MagicMock(), upload_wait_timeout=2000)
        with unittest.mock.patch.object(uploader, "_wait_for_obscuring_elements"), \
             unittest.mock.patch.object(
                 uploader, "_per_file_queue_signal_count", return_value=0
             ), \
             unittest.mock.patch.object(
                 uploader, "_has_batch_upload_status", return_value=True
             ), \
             unittest.mock.patch.object(uploader._page, "wait_for_timeout"):
            uploader._wait_until_queued_count(use_zip=False, expected=1)

    def test_wait_until_queued_count_ignores_batch_message_for_file_two(self) -> None:
        uploader = DataLumosFileUploader(MagicMock(), upload_wait_timeout=500)
        call_count = {"n": 0}

        def queue_count(_use_zip: bool) -> int:
            call_count["n"] += 1
            return 1

        with unittest.mock.patch.object(uploader, "_wait_for_obscuring_elements"), \
             unittest.mock.patch.object(
                 uploader, "_per_file_queue_signal_count", side_effect=queue_count
             ), \
             unittest.mock.patch.object(
                 uploader, "_has_batch_upload_status", return_value=True
             ), \
             unittest.mock.patch.object(uploader._page, "wait_for_timeout"):
            with self.assertRaises(TimeoutError):
                uploader._wait_until_queued_count(use_zip=False, expected=2)
        self.assertGreater(call_count["n"], 1)

    def test_per_file_queue_count_ignores_batch_processing_phrase(self) -> None:
        uploader = DataLumosFileUploader(MagicMock())
        with unittest.mock.patch.object(
            uploader,
            "_modal_status_text",
            return_value="Uploaded files are being processed...",
        ), unittest.mock.patch.object(uploader, "_element_phrase_count", return_value=0):
            self.assertEqual(uploader._per_file_queue_signal_count(use_zip=False), 0)

    def test_per_file_queue_count_matches_queue_phrase(self) -> None:
        uploader = DataLumosFileUploader(MagicMock())
        text = FILE_PER_FILE_QUEUE_PHRASES[0] + "\n" + FILE_PER_FILE_QUEUE_PHRASES[0]
        with unittest.mock.patch.object(
            uploader, "_modal_status_text", return_value=text
        ), unittest.mock.patch.object(uploader, "_element_phrase_count", return_value=0):
            self.assertEqual(uploader._per_file_queue_signal_count(use_zip=False), 2)

    def test_close_modal_skips_busy_wait_when_configured(self) -> None:
        mock_page = MagicMock()
        modal = MagicMock()
        modal.count.return_value = 1
        modal.first.is_visible.return_value = True
        busy = MagicMock()
        busy.count.return_value = 0
        close_btn = MagicMock()

        def locator_side_effect(selector: str) -> MagicMock:
            if selector == ".importFileModal":
                return modal
            if selector == "#busy":
                return busy
            return close_btn

        mock_page.locator.side_effect = locator_side_effect
        uploader = DataLumosFileUploader(mock_page, skip_busy_wait_on_close=True)
        uploader._close_modal(use_zip=False)
        close_btn.click.assert_called_once()
        busy.first.wait_for.assert_not_called()
        mock_page.wait_for_timeout.assert_called_with(500)

    def test_close_modal_skips_when_modal_already_closed(self) -> None:
        mock_page = MagicMock()
        modal = MagicMock()
        modal.count.return_value = 0
        close_btn = MagicMock()

        def locator_side_effect(selector: str) -> MagicMock:
            if selector == ".importFileModal":
                return modal
            return close_btn

        mock_page.locator.side_effect = locator_side_effect
        uploader = DataLumosFileUploader(mock_page)
        uploader._close_modal(use_zip=False)
        close_btn.click.assert_not_called()
