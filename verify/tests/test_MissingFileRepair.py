"""
Unit tests for MissingFileRepair helpers and repair flow.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from utils.Args import Args
from utils.Logger import Logger
from verify.DatalumosViewFileStats import DatalumosViewFileStats
from verify.MissingFileRepair import (
    STATUS_RE_UPLOADED,
    MissingFileRepair,
    ensure_file_on_disk,
    missing_publication_files,
    resolve_project_folder,
    should_attempt_missing_file_repair,
)


class TestMissingFileRepairHelpers(unittest.TestCase):
    """Tests for pure helpers used by missing-file repair."""

    def setUp(self) -> None:
        """Initialize Args for folder resolution tests."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "verify_upload"]
        Args.initialize()
        Logger.initialize(log_level="ERROR", log_file=False)

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    def test_should_attempt_when_dl_count_lower(self) -> None:
        """Repair is offered only when DataLumos has fewer files than the DB."""
        stats = DatalumosViewFileStats(file_count=4, total_bytes=100)
        self.assertTrue(should_attempt_missing_file_repair(5, stats))
        self.assertFalse(should_attempt_missing_file_repair(4, stats))
        self.assertFalse(should_attempt_missing_file_repair(3, stats))
        self.assertFalse(
            should_attempt_missing_file_repair(5, DatalumosViewFileStats(error="x"))
        )

    def test_missing_publication_files_case_insensitive(self) -> None:
        """Catalog files already on DL (any case) are not missing."""
        pubs = [
            ("Data.zip", "https://example.com/a.zip", 100),
            ("readme.txt", "https://example.com/r.txt", 10),
        ]
        missing = missing_publication_files(pubs, ["data.zip", "other.pdf"])
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0][0], "readme.txt")

    def test_resolve_project_folder_prefers_stored_path(self) -> None:
        """Stored folder_path wins over base_output_dir default."""
        folder = resolve_project_folder(12, r"C:\Data\DRP000012")
        self.assertEqual(folder, Path(r"C:\Data\DRP000012"))

    def test_resolve_project_folder_default(self) -> None:
        """Without folder_path, use base_output_dir/{sheet prefix}######."""
        with patch("utils.file_utils._configured_output_folder_prefix", return_value="USFS"), patch.object(
            Args, "base_output_dir", r"C:\Out"
        ):
            folder = resolve_project_folder(7, None)
        self.assertEqual(folder, Path(r"C:\Out") / "USFS000007")

    def test_ensure_file_on_disk_skips_existing(self) -> None:
        """Existing files are not re-downloaded."""
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            dest = folder / "a.zip"
            dest.write_bytes(b"abc")
            with patch("verify.MissingFileRepair.download_via_url") as mock_dl:
                path = ensure_file_on_disk(
                    folder,
                    "a.zip",
                    "https://example.com/a.zip",
                    3,
                    drpid=1,
                )
            mock_dl.assert_not_called()
            self.assertEqual(path, dest)

    def test_ensure_file_on_disk_downloads_when_missing(self) -> None:
        """Missing files are downloaded via HTTP for sub-1GB sizes."""
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)

            def _fake_download(url: str, dest: Path, **kwargs: object) -> tuple[int, bool]:
                dest.write_bytes(b"data")
                return 4, True

            with patch(
                "verify.MissingFileRepair.download_via_url",
                side_effect=_fake_download,
            ) as mock_dl:
                path = ensure_file_on_disk(
                    folder,
                    "a.zip",
                    "https://example.com/a.zip",
                    100,
                    drpid=1,
                )
            mock_dl.assert_called_once()
            self.assertTrue(path.is_file())


class TestMissingFileRepairFlow(unittest.TestCase):
    """Tests for MissingFileRepair.repair orchestration."""

    def setUp(self) -> None:
        """Initialize logger."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "verify_upload"]
        Args.initialize()
        Logger.initialize(log_level="ERROR", log_file=False)

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    @patch("verify.MissingFileRepair.ensure_file_on_disk")
    @patch("verify.MissingFileRepair.fetch_catalog_publication_files")
    def test_repair_uploads_missing_and_returns_true(
        self,
        mock_fetch: MagicMock,
        mock_ensure: MagicMock,
    ) -> None:
        """Repair downloads missing catalog files and uploads them."""
        mock_fetch.return_value = [
            ("big.zip", "https://example.com/big.zip", 1000),
            ("small.txt", "https://example.com/small.txt", 10),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            big = folder / "big.zip"
            big.write_bytes(b"x")
            mock_ensure.return_value = big

            session = MagicMock()
            page = MagicMock()
            session.ensure_browser.return_value = page
            repairer = MissingFileRepair(session)
            call_order: list[str] = []
            session.reauthenticate.side_effect = lambda: call_order.append("reauth")
            repairer._upload_paths = MagicMock(  # type: ignore[method-assign]
                side_effect=lambda *_a, **_k: call_order.append("upload")
            )

            project = {
                "source_url": "https://example.gov/catalog/RDS-1",
                "datalumos_id": "99",
                "folder_path": str(folder),
            }
            stats = DatalumosViewFileStats(
                file_count=1,
                total_bytes=10,
                file_names=("small.txt",),
            )
            self.assertTrue(repairer.repair(5, project, stats))
            mock_fetch.assert_called_once_with(
                "https://example.gov/catalog/RDS-1", page=page
            )
            mock_ensure.assert_called_once()
            repairer._upload_paths.assert_called_once_with("99", [big])
            self.assertEqual(call_order, ["reauth", "upload", "reauth"])

    @patch("verify.MissingFileRepair.fetch_catalog_publication_files")
    def test_repair_returns_false_when_no_missing_names(
        self, mock_fetch: MagicMock
    ) -> None:
        """When catalog names are already on DL, repair is a no-op."""
        mock_fetch.return_value = [
            ("a.zip", "https://example.com/a.zip", 100),
        ]
        repairer = MissingFileRepair(MagicMock())
        project = {
            "source_url": "https://example.gov/catalog/RDS-1",
            "datalumos_id": "99",
            "folder_path": r"C:\data",
        }
        stats = DatalumosViewFileStats(
            file_count=1,
            total_bytes=100,
            file_names=("a.zip", "extra.pdf"),
        )
        self.assertFalse(repairer.repair(5, project, stats))

    def test_status_constant(self) -> None:
        """Re-uploaded status string is stable for Storage updates."""
        self.assertEqual(STATUS_RE_UPLOADED, "re-uploaded")


if __name__ == "__main__":
    unittest.main()
