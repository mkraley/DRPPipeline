"""Tests for scripts.download_large_files and export ensure helper."""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from utils.Logger import Logger

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestEnsureDrpidAria2Cmd(unittest.TestCase):
    def test_ensure_skips_export_when_cmd_has_lines(self) -> None:
        from scripts.export_usfs_aria2_input import ensure_drpid_aria2_cmd

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "aria2_inputs"
            out_dir.mkdir()
            cmd_path = out_dir / "DRP000042.cmd"
            cmd_path.write_text(
                '@echo off\naria2c -c -d "C:\\data" -o "big.zip" "https://example.com/x"\n',
                encoding="utf-8",
            )
            conn = sqlite3.connect(":memory:")
            with patch("scripts.export_usfs_aria2_input.export_drpid") as mock_export:
                path, count = ensure_drpid_aria2_cmd(
                    conn,
                    42,
                    output_dir=out_dir,
                    base_output_dir=Path(tmp),
                    user_agent="UA",
                    min_bytes=1,
                    missing_only=True,
                )
            mock_export.assert_not_called()
            self.assertEqual(path, cmd_path)
            self.assertEqual(count, 1)
            conn.close()

    def test_ensure_finds_bts_prefixed_cmd(self) -> None:
        """Sheet-name prefix BTS resolves BTS000007.cmd without re-export."""
        from scripts.export_usfs_aria2_input import ensure_drpid_aria2_cmd

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "aria2_inputs"
            out_dir.mkdir()
            cmd_path = out_dir / "BTS000007.cmd"
            cmd_path.write_text(
                '@echo off\naria2c -c -d "C:\\data" -o "big.zip" "https://example.com/x"\n',
                encoding="utf-8",
            )
            conn = sqlite3.connect(":memory:")
            with patch("scripts.export_usfs_aria2_input.export_drpid") as mock_export:
                path, count = ensure_drpid_aria2_cmd(
                    conn,
                    7,
                    output_dir=out_dir,
                    base_output_dir=Path(tmp),
                    user_agent="UA",
                    min_bytes=1,
                    missing_only=True,
                    sheet_name="BTS",
                )
            mock_export.assert_not_called()
            self.assertEqual(path, cmd_path)
            self.assertEqual(count, 1)
            conn.close()

    def test_ensure_exports_when_cmd_missing(self) -> None:
        from scripts.export_usfs_aria2_input import ensure_drpid_aria2_cmd

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "aria2_inputs"
            out_dir.mkdir()
            conn = sqlite3.connect(":memory:")
            with patch("scripts.export_usfs_aria2_input.export_drpid", return_value=2) as mock_export:
                path, count = ensure_drpid_aria2_cmd(
                    conn,
                    42,
                    output_dir=out_dir,
                    base_output_dir=Path(tmp),
                    user_agent="UA",
                    min_bytes=1,
                    missing_only=True,
                )
            mock_export.assert_called_once()
            self.assertEqual(count, 2)
            self.assertEqual(path, out_dir / "DRP000042.cmd")
            conn.close()


class TestLoadConfigHelpers(unittest.TestCase):
    """Config loaders must honor sources.<source> overrides."""

    def test_load_helpers_use_selected_source_section(self) -> None:
        from scripts.export_usfs_aria2_input import (
            load_base_output_dir,
            load_db_path,
            load_google_sheet_name,
        )

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                '{"source": "bts", "sources": {'
                '"bts": {'
                '"db_path": "bts.db",'
                '"base_output_dir": "C:\\\\DataRescue\\\\BTSData",'
                '"google_sheet_name": "BTS"'
                "}}}",
                encoding="utf-8",
            )
            self.assertEqual(load_google_sheet_name(config_path), "BTS")
            self.assertEqual(load_db_path(config_path), REPO_ROOT / "bts.db")
            self.assertEqual(
                load_base_output_dir(config_path),
                Path(r"C:\DataRescue\BTSData"),
            )

class TestDownloadCmdLineRouting(unittest.TestCase):
    """ROSA P lines use Chrome Ranges; other hosts keep aria2."""

    @classmethod
    def setUpClass(cls) -> None:
        Logger.initialize(log_level="WARNING")

    def test_rosap_uses_chrome_range_downloader(self) -> None:
        from scripts.download_large_files import download_cmd_line

        with tempfile.TemporaryDirectory() as tmp:
            dest_dir = Path(tmp)
            line = (
                'aria2c -c -x 8 -s 8 -j 1 --file-allocation=none --max-tries=0 '
                '--retry-wait=10 --user-agent="Mozilla/5.0" '
                f'-d "{dest_dir}" -o "file.zip" '
                '"https://rosap.ntl.bts.gov/view/dot/1/file.zip"'
            )

            def _fake_chrome(_url: str, dest: Path) -> tuple[int, bool]:
                dest.write_bytes(b"12345")
                return 5, True

            with patch(
                "utils.ChromeRangeDownload.probe_content_length", return_value=5
            ), patch(
                "utils.ChromeRangeDownload.download_via_chrome_ranges",
                side_effect=_fake_chrome,
            ) as mock_chrome:
                ok, attempts = download_cmd_line(
                    line,
                    log_path=dest_dir / "x.log",
                    summary_interval=0,
                    max_attempts=3,
                    page_downloader=None,
                )
        self.assertTrue(ok)
        self.assertEqual(attempts, 1)
        mock_chrome.assert_called_once()

    def test_non_rosap_uses_aria2(self) -> None:
        from scripts.download_large_files import download_cmd_line

        line = (
            'aria2c -c -x 4 -s 4 -j 1 --file-allocation=none --max-tries=0 '
            '--retry-wait=10 --user-agent="Mozilla/5.0" '
            '-d "C:\\data" -o "big.zip" '
            '"https://www.fs.usda.gov/rds/archive/products/RDS/big.zip"'
        )
        with patch(
            "collectors.UsfsAria2Export.run_aria2_cmd_line_with_retries",
            return_value=(True, 1),
        ) as mock_aria2:
            ok, attempts = download_cmd_line(
                line,
                log_path=Path("x.log"),
                summary_interval=0,
                max_attempts=3,
                page_downloader=None,
            )
        self.assertTrue(ok)
        self.assertEqual(attempts, 1)
        mock_aria2.assert_called_once()


class TestDownloadLargeFilesRunDrpid(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Logger.initialize(log_level="WARNING")

    def test_run_drpid_retries_on_failure(self) -> None:
        from scripts.download_large_files import run_drpid

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "aria2_inputs"
            out_dir.mkdir()
            cmd_path = out_dir / "DRP000007.cmd"
            cmd_path.write_text(
                '@echo off\n'
                'aria2c -c -x 4 -s 4 -j 1 --file-allocation=none --max-tries=0 '
                '--retry-wait=10 --user-agent="UA" -d "C:\\data" -o "big.zip" '
                '"https://example.com/big.zip"\n',
                encoding="utf-8",
            )
            conn = sqlite3.connect(":memory:")
            mock_retry = MagicMock(return_value=(True, 2))
            with patch(
                "collectors.UsfsAria2Export.run_aria2_cmd_line_with_retries",
                mock_retry,
            ):
                code = run_drpid(
                    7,
                    conn=conn,
                    aria2_inputs_dir=out_dir,
                    base_output_dir=Path(tmp),
                    log_root=Path(tmp) / "logs",
                    summary_interval=0,
                    stop_on_error=False,
                    max_attempts=3,
                    min_bytes=1,
                    missing_only=True,
                )
            self.assertEqual(code, 0)
            mock_retry.assert_called_once()
            conn.close()

    def test_main_initializes_logger(self) -> None:
        """CLI entry must initialize Logger before ROSA P downloads."""
        from scripts import download_large_files as mod

        with patch.object(mod, "run_drpid", return_value=0), patch.object(
            mod.sqlite3, "connect"
        ) as mock_connect, patch.object(
            mod, "load_base_output_dir", return_value=Path("C:\\tmp")
        ), patch.object(
            mod, "load_google_sheet_name", return_value="BTS"
        ), patch.object(
            mod, "load_db_path", return_value=Path("bts.db")
        ), patch.object(
            mod.Logger, "initialize"
        ) as mock_log_init, patch(
            "sys.argv", ["download_large_files.py", "7"]
        ):
            mock_connect.return_value = MagicMock()
            code = mod.main()
        self.assertEqual(code, 0)
        mock_log_init.assert_called_once_with(log_level="INFO")


if __name__ == "__main__":
    unittest.main()
