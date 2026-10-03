"""Unit tests for UploadLargeFiles module."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from storage import Storage
from upload.UploadLargeFiles import (
    DISK_SPACE_BUFFER_BYTES,
    MAX_PROJECT_FILE_SIZE_BYTES,
    STATUS_FINISH_WAIT,
    STATUS_UPLOADED_EXPANDED,
    STATUS_UPLOADED_LARGE_FILE,
    UPLOAD_LARGE_FILES_TIMEOUT_MS,
    WORKSPACE_LOAD_TIMEOUT_MS,
    UploadLargeFiles,
    bytes_still_to_download,
    ensure_disk_space_for_download,
    is_eligible_for_upload_large_files,
    parse_max_project_size,
    planned_download_paths,
    planned_out_names,
    project_under_size_limit,
    run_aria2_downloads,
)
from utils.Errors import PipelineFatal
from utils.Args import Args
from utils.Logger import Logger


class TestUploadLargeFilesHelpers(unittest.TestCase):
    def test_upload_timeout_is_two_hours(self) -> None:
        self.assertEqual(UPLOAD_LARGE_FILES_TIMEOUT_MS, 2 * 60 * 60 * 1000)

    def test_workspace_load_timeout_is_sixty_minutes(self) -> None:
        self.assertEqual(WORKSPACE_LOAD_TIMEOUT_MS, 60 * 60 * 1000)

    def test_project_under_size_limit(self) -> None:
        under = {"file_size": "10.0 GB"}
        at_limit = {"file_size": format_bytes(MAX_PROJECT_FILE_SIZE_BYTES)}
        over = {"file_size": format_bytes(MAX_PROJECT_FILE_SIZE_BYTES + 1)}
        missing = {"file_size": None}

        self.assertTrue(project_under_size_limit(under))
        self.assertFalse(project_under_size_limit(at_limit))
        self.assertFalse(project_under_size_limit(over))
        self.assertFalse(project_under_size_limit(missing))

    def test_parse_max_project_size_bare_number_is_gigabytes(self) -> None:
        self.assertEqual(parse_max_project_size(40), 40 * 1024**3)
        self.assertEqual(parse_max_project_size("40GB"), 40 * 1024**3)
        self.assertEqual(parse_max_project_size("40 GB"), 40 * 1024**3)

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

    def test_planned_download_paths_keep_product_folders(self) -> None:
        """``-d`` product folders are part of the path that will be uploaded."""
        lines = [
            'aria2c --user-agent="UA" -d "C:\\DataRescue\\NPSData\\NPS001502" '
            '-o "LAVO_SRI_Enhanced.rar" "https://irma.nps.gov/DataStore/DownloadFile/1"',
            'aria2c --user-agent="UA" '
            '-d "C:\\DataRescue\\NPSData\\NPS001502\\Soil_Survey" '
            '-o "LAVO_Soil_Survey_Report.zip" '
            '"https://irma.nps.gov/DataStore/DownloadFile/2"',
        ]
        paths = planned_download_paths(lines)
        self.assertEqual(paths[0].name, "LAVO_SRI_Enhanced.rar")
        self.assertEqual(paths[1].parent.name, "Soil_Survey")
        self.assertEqual(paths[1].name, "LAVO_Soil_Survey_Report.zip")


class TestEnsureAria2CmdSkipNoteFallback(unittest.TestCase):
    """ensure_aria2_cmd builds commands from status_notes for non-USFS sources."""

    def setUp(self) -> None:
        """Use DRP prefix so aria2 cmd paths match test fixtures."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "noop"]
        Args.initialize()
        Args._config["google_sheet_name"] = "DRP"
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        sys.argv = self._original_argv

    @patch("upload.UploadLargeFiles.parse_data_access_links", return_value={"publication_files": []})
    @patch("upload.UploadLargeFiles.fetch_page_body", return_value=(200, "<html></html>", None, None))
    def test_uses_status_notes_when_catalog_empty(
        self, _mock_fetch: MagicMock, _mock_parse: MagicMock
    ) -> None:
        from upload.UploadLargeFiles import ensure_aria2_cmd

        notes = (
            "Skipped download (>1GB): A01L4_1.zip (2.9 GB) - "
            "download manually: https://ndownloader.figshare.com/files/43634028"
        )
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "DRP000157"
            out_dir = Path(tmp) / "aria2_inputs"
            project = {
                "source_url": "https://agdatacommons.nal.usda.gov/articles/dataset/x/1",
                "folder_path": str(folder),
                "status_notes": notes,
            }
            with patch("upload.UploadLargeFiles.DEFAULT_ARIA2_OUTPUT_DIR", out_dir):
                cmd_path, lines = ensure_aria2_cmd(157, project)

            self.assertTrue(cmd_path.is_file())
            joined = "\n".join(lines)
            self.assertIn("43634028", joined)
            self.assertIn("A01L4_1.zip", joined)

    @patch("upload.UploadLargeFiles.parse_data_access_links", return_value={"publication_files": []})
    @patch("upload.UploadLargeFiles.fetch_page_body", return_value=(200, "<html></html>", None, None))
    def test_uses_status_notes_for_sub_gb_deferred_files(
        self, _mock_fetch: MagicMock, _mock_parse: MagicMock
    ) -> None:
        """Skip-note fallback exports deferred files under 1 GB each for aria2."""
        from upload.UploadLargeFiles import ensure_aria2_cmd

        notes = (
            "Skipped download (>1GB): part2.zip (400.0 MB) - "
            "download manually: https://example.com/part2.zip\n"
            "Skipped download (>1GB): readme.txt - "
            "download manually: https://example.com/readme.txt"
        )
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "DRP000158"
            out_dir = Path(tmp) / "aria2_inputs"
            project = {
                "source_url": "https://rosap.ntl.bts.gov/view/dot/158",
                "folder_path": str(folder),
                "status_notes": notes,
            }
            with patch("upload.UploadLargeFiles.DEFAULT_ARIA2_OUTPUT_DIR", out_dir):
                cmd_path, lines = ensure_aria2_cmd(158, project)

            self.assertTrue(cmd_path.is_file())
            joined = "\n".join(lines)
            self.assertIn("part2.zip", joined)
            self.assertIn("readme.txt", joined)


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
            self.assertIn("25.0 GB", mock_error.call_args[0][1])

    def test_run_accepts_project_under_raised_cap(self) -> None:
        """--max-project-size lets a project above 25 GB through the size check."""
        Args._config["max_project_size"] = "40GB"
        drpid = Storage.create_record("https://example.com/test")
        Storage.update_record(
            drpid,
            {
                "status": STATUS_UPLOADED_LARGE_FILE,
                "datalumos_id": "123",
                "folder_path": str(self.temp_dir),
                "file_size": "30.0 GB",
            },
        )
        with patch("upload.UploadLargeFiles.ensure_aria2_cmd", return_value=(Path("x.cmd"), [])), patch(
            "upload.UploadLargeFiles.large_files_on_disk", return_value=[]
        ), patch("upload.UploadIssueReporter.record_error") as mock_error:
            self.module.run(drpid)
        messages = " ".join(item.args[1] for item in mock_error.call_args_list)
        self.assertNotIn("40.0 GB", messages)
        self.assertIn("No large files", messages)

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
        file_paths = mock_upload.call_args[0][3]
        self.assertEqual([p.name for p in file_paths], ["big.zip"])
        mock_storage.update_record.assert_called_with(7, {"status": STATUS_FINISH_WAIT})

    def test_run_aria2_downloads_uses_chrome_ranges_for_rosap(self) -> None:
        """ROSA P lines must use Chrome Range download, not aria2."""
        with tempfile.TemporaryDirectory() as tmp:
            dest_dir = Path(tmp) / "out"
            dest_dir.mkdir()
            line = (
                'aria2c -c -x 8 -s 8 -j 1 --file-allocation=none --max-tries=0 '
                '--retry-wait=10 --user-agent="Mozilla/5.0" '
                f'-d "{dest_dir}" -o "file.zip" '
                '"https://rosap.ntl.bts.gov/view/dot/1/file.zip"'
            )

            def _fake_chrome(_url: str, dest: Path) -> tuple[int, bool]:
                dest.write_bytes(b"hello")
                return 5, True

            with patch(
                "utils.ChromeRangeDownload.probe_content_length", return_value=5
            ), patch(
                "utils.ChromeRangeDownload.download_via_chrome_ranges",
                side_effect=_fake_chrome,
            ) as mock_chrome:
                with patch(
                    "collectors.UsfsAria2Export.run_aria2_cmd_line_with_retries"
                ) as mock_aria2:
                    ok, fail = run_aria2_downloads(
                        1,
                        [line],
                        log_root=Path(tmp) / "logs",
                    )
            self.assertEqual(ok, 1)
            self.assertEqual(fail, 0)
            mock_aria2.assert_not_called()
            mock_chrome.assert_called_once()
            self.assertTrue((dest_dir / "file.zip").is_file())


class TestDownloadDiskSpace(unittest.TestCase):
    """Free space must cover files still to download plus a 50 GB buffer."""

    def test_bytes_still_to_download_uses_skip_note_sizes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            partial = folder / "big.zip"
            partial.write_bytes(b"x" * 100)
            project = {
                "status_notes": (
                    "Skipped download (>1GB): big.zip (10 GB) - "
                    "download manually: https://example.com/big.zip"
                ),
                "file_size": "10 GB",
            }
            needed = bytes_still_to_download(project, folder, [partial])
        self.assertEqual(needed, 10 * 1024**3 - 100)

    def test_ensure_disk_space_raises_when_buffer_would_be_used(self) -> None:
        needed = 10 * 1024**3
        usage = MagicMock(free=needed + DISK_SPACE_BUFFER_BYTES - 1)
        with tempfile.TemporaryDirectory() as tmp:
            with patch("upload.UploadLargeFiles.shutil.disk_usage", return_value=usage):
                with self.assertRaises(PipelineFatal) as ctx:
                    ensure_disk_space_for_download(Path(tmp), needed)
        self.assertIn("Not enough disk space", str(ctx.exception))

    def test_ensure_disk_space_allows_exact_buffer(self) -> None:
        needed = 10 * 1024**3
        usage = MagicMock(free=needed + DISK_SPACE_BUFFER_BYTES)
        with tempfile.TemporaryDirectory() as tmp:
            with patch("upload.UploadLargeFiles.shutil.disk_usage", return_value=usage):
                ensure_disk_space_for_download(Path(tmp), needed)


if __name__ == "__main__":
    unittest.main()
