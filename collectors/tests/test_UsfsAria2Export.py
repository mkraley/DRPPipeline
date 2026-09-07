"""Tests for collectors.UsfsAria2Export helpers."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from collectors.UsfsAria2Export import (
    Aria2Entry,
    MAX_DOWNLOAD_BYTES,
    aria2_argv_for_download,
    aria2_cmd_download_parts,
    download_exported_cmd_line,
    entries_for_publication_files,
    format_windows_command,
    format_windows_commands,
    is_usfs_catalog_maintenance_page,
    max_connections_for_url,
    out_name_from_aria2_cmd_line,
    parse_aria2_windows_cmd_line,
    parse_aria2c_lines_from_cmd_text,
    requires_browser_download,
    run_aria2_cmd_line_with_retries,
    write_drpid_aria2_cmd,
)
from utils.Args import Args
from utils.Logger import Logger
from utils.url_utils import BROWSER_HEADERS


class TestUsfsAria2Export(unittest.TestCase):
    def setUp(self) -> None:
        """Use a stable folder prefix so cmd paths are predictable."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "noop"]
        Args.initialize()
        Args._config["google_sheet_name"] = "DRP"
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        sys.argv = self._original_argv

    def test_max_connections_for_url(self) -> None:
        self.assertEqual(
            max_connections_for_url("https://usfs-public.box.com/shared/static/x.zip"),
            16,
        )
        self.assertEqual(
            max_connections_for_url("https://www.fs.usda.gov/rds/archive/products/RDS/x.zip"),
            4,
        )

    def test_requires_browser_download_for_rosap(self) -> None:
        """ROSA P hosts need Playwright; USDA product URLs do not."""
        self.assertTrue(
            requires_browser_download(
                "https://rosap.ntl.bts.gov/view/dot/78551/dot_78551_DS1.zip"
            )
        )
        self.assertFalse(
            requires_browser_download(
                "https://www.fs.usda.gov/rds/archive/products/RDS/x.zip"
            )
        )

    def test_aria2_cmd_download_parts(self) -> None:
        """Parse URL, -d, and -o from an exported aria2c line."""
        line = (
            'aria2c -c -x 8 -s 8 -j 1 --file-allocation=none --max-tries=0 '
            '--retry-wait=10 --user-agent="Mozilla/5.0" '
            '-d "C:\\DataRescue\\BTSData\\BTS000007" -o "dot_78551_DS1.zip" '
            '"https://rosap.ntl.bts.gov/view/dot/78551/dot_78551_DS1.zip"'
        )
        url, dest_dir, out_name = aria2_cmd_download_parts(line)
        self.assertEqual(url, "https://rosap.ntl.bts.gov/view/dot/78551/dot_78551_DS1.zip")
        self.assertEqual(dest_dir, Path(r"C:\DataRescue\BTSData\BTS000007"))
        self.assertEqual(out_name, "dot_78551_DS1.zip")

    def test_download_exported_cmd_line_rosap_uses_chrome_ranges(self) -> None:
        """ROSA P URLs call Chrome Range download instead of aria2."""
        with tempfile.TemporaryDirectory() as tmp:
            dest_dir = Path(tmp)
            line = (
                'aria2c -c -x 8 -s 8 -j 1 --file-allocation=none --max-tries=0 '
                '--retry-wait=10 --user-agent="Mozilla/5.0" '
                f'-d "{dest_dir}" -o "file.zip" '
                '"https://rosap.ntl.bts.gov/view/dot/1/file.zip"'
            )

            def _fake_chrome(_url: str, dest: Path) -> tuple[int, bool]:
                dest.write_bytes(b"data")
                return 4, True

            with patch(
                "utils.ChromeRangeDownload.probe_content_length", return_value=4
            ), patch(
                "utils.ChromeRangeDownload.download_via_chrome_ranges",
                side_effect=_fake_chrome,
            ) as mock_chrome, patch(
                "collectors.UsfsAria2Export.run_aria2_cmd_line_with_retries"
            ) as mock_aria2:
                ok, attempts = download_exported_cmd_line(
                    line,
                    log_path=dest_dir / "x.log",
                    page_downloader=None,
                )
            self.assertTrue(ok)
            self.assertEqual(attempts, 1)
            mock_aria2.assert_not_called()
            mock_chrome.assert_called_once()

    def test_download_exported_cmd_line_non_rosap_uses_aria2(self) -> None:
        """Non-ROSA P hosts keep aria2 retries."""
        line = (
            'aria2c -c -x 4 -s 4 -j 1 --file-allocation=none --max-tries=0 '
            '--retry-wait=10 --user-agent="Mozilla/5.0" '
            '-d "C:\\data" -o "big.zip" '
            '"https://www.fs.usda.gov/rds/archive/products/RDS/big.zip"'
        )
        with patch(
            "collectors.UsfsAria2Export.run_aria2_cmd_line_with_retries",
            return_value=(True, 2),
        ) as mock_aria2:
            ok, attempts = download_exported_cmd_line(
                line,
                log_path=Path("x.log"),
                page_downloader=None,
            )
        self.assertTrue(ok)
        self.assertEqual(attempts, 2)
        mock_aria2.assert_called_once()

    def test_is_usfs_catalog_maintenance_page(self) -> None:
        """Detect the USFS maintenance placeholder page."""
        self.assertTrue(
            is_usfs_catalog_maintenance_page(
                "Database currently under maintenance. Please try again later."
            )
        )
        self.assertFalse(is_usfs_catalog_maintenance_page("<dt>Data Access</dt>"))

    def test_entries_for_publication_files_skips_on_disk(self) -> None:
        folder = Path(__file__).parent / "_tmp_aria2_export"
        folder.mkdir(exist_ok=True)
        big = MAX_DOWNLOAD_BYTES + 1
        small = 100
        existing = folder / "have.zip"
        existing.write_bytes(b"x" * 10)
        try:
            entries = entries_for_publication_files(
                [
                    ("have.zip", "https://example.com/have.zip", big),
                    ("need.zip", "https://example.com/need.zip", big),
                    ("tiny.zip", "https://example.com/tiny.zip", small),
                ],
                folder,
                missing_only=True,
            )
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].out_name, "need.zip")
            self.assertEqual(entries[0].max_connections, 8)
        finally:
            for p in folder.iterdir():
                p.unlink()
            folder.rmdir()

    def test_format_windows_command(self) -> None:
        entry = Aria2Entry(
            url="https://usfs-public.box.com/shared/static/a.zip",
            out_name="big.zip",
            dir_path=Path(r"C:\data\DRP000017"),
            max_connections=16,
        )
        ua = "Mozilla/5.0 Test"
        line = format_windows_command(entry, ua)
        self.assertIn("aria2c -c -x 16 -s 16", line)
        self.assertIn('-d "C:\\data\\DRP000017"', line)
        self.assertIn('-o "big.zip"', line)
        self.assertIn("https://usfs-public.box.com/shared/static/a.zip", line)
        self.assertIn('--user-agent="Mozilla/5.0 Test"', line)

    def test_format_windows_commands_batch(self) -> None:
        entry = Aria2Entry(
            url="https://example.com/need.zip",
            out_name="need.zip",
            dir_path=Path(r"C:\data\DRP000001"),
            max_connections=8,
        )
        text = format_windows_commands([entry], "UA", drpid=1)
        self.assertIn("@echo off", text)
        self.assertIn("REM DRPID 1", text)
        self.assertIn("echo Downloading need.zip", text)
        self.assertIn("if errorlevel 1 exit /b 1", text)

    def test_parse_aria2c_lines_from_cmd_text(self) -> None:
        text = (
            "@echo off\n"
            "echo Downloading big.zip ...\n"
            'aria2c -c -d "C:\\data" -o "big.zip" "https://example.com/x.zip"\n'
            "if errorlevel 1 exit /b 1\n"
        )
        lines = parse_aria2c_lines_from_cmd_text(text)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("aria2c "))

    def test_parse_aria2_windows_cmd_line_user_agent_parens(self) -> None:
        ua = BROWSER_HEADERS["User-Agent"]
        cmd = format_windows_command(
            Aria2Entry(
                url="https://usfs-public.box.com/shared/static/x.zip",
                out_name="RDS-2025-0031.zip",
                dir_path=Path(r"C:\Documents\DataRescue\USFSData\DRP000030"),
                max_connections=16,
            ),
            ua,
        )
        argv = parse_aria2_windows_cmd_line(cmd)
        self.assertEqual(argv[0], "aria2c")
        ua_arg = next(a for a in argv if a.startswith("--user-agent="))
        self.assertIn("(Windows NT", ua_arg)
        self.assertEqual(argv[argv.index("-o") + 1], "RDS-2025-0031.zip")
        self.assertTrue(argv[-1].startswith("https://"))

    def test_aria2_argv_for_download(self) -> None:
        ua = BROWSER_HEADERS["User-Agent"]
        cmd = format_windows_command(
            Aria2Entry(
                url="https://example.com/file.zip",
                out_name="file.zip",
                dir_path=Path(r"C:\data\DRP000029"),
                max_connections=16,
            ),
            ua,
        )
        log_path = Path(r"C:\logs\DRP000029\file.zip.log")
        argv = aria2_argv_for_download(cmd, log_path=log_path, summary_interval=0)
        self.assertIn("--console-log-level=warn", argv)
        self.assertIn("--show-console-readout=true", argv)
        self.assertIn("--summary-interval=0", argv)
        self.assertIn(f"--log={log_path}", argv)
        self.assertEqual(out_name_from_aria2_cmd_line(cmd), "file.zip")

    def test_run_aria2_cmd_line_with_retries_succeeds_first_try(self) -> None:
        from unittest.mock import MagicMock, patch

        ua = BROWSER_HEADERS["User-Agent"]
        cmd = format_windows_command(
            Aria2Entry(
                url="https://example.com/file.zip",
                out_name="file.zip",
                dir_path=Path(r"C:\data\DRP000029"),
                max_connections=8,
            ),
            ua,
        )
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with patch("collectors.UsfsAria2Export.subprocess.run", mock_run):
            ok, attempts = run_aria2_cmd_line_with_retries(
                cmd,
                log_path=Path(r"C:\logs\file.zip.log"),
            )
        self.assertTrue(ok)
        self.assertEqual(attempts, 1)
        self.assertEqual(mock_run.call_count, 1)

    def test_run_aria2_cmd_line_with_retries_retries_until_success(self) -> None:
        from unittest.mock import MagicMock, patch

        ua = BROWSER_HEADERS["User-Agent"]
        cmd = format_windows_command(
            Aria2Entry(
                url="https://example.com/file.zip",
                out_name="file.zip",
                dir_path=Path(r"C:\data\DRP000029"),
                max_connections=8,
            ),
            ua,
        )
        mock_run = MagicMock(
            side_effect=[MagicMock(returncode=1), MagicMock(returncode=1), MagicMock(returncode=0)]
        )
        with patch("collectors.UsfsAria2Export.subprocess.run", mock_run):
            ok, attempts = run_aria2_cmd_line_with_retries(
                cmd,
                log_path=Path(r"C:\logs\file.zip.log"),
                max_attempts=3,
            )
        self.assertTrue(ok)
        self.assertEqual(attempts, 3)
        self.assertEqual(mock_run.call_count, 3)

    def test_write_drpid_aria2_cmd(self) -> None:
        folder = Path(__file__).parent / "_tmp_aria2_write"
        folder.mkdir(exist_ok=True)
        out_dir = Path(__file__).parent / "_tmp_aria2_out"
        big = MAX_DOWNLOAD_BYTES + 1
        try:
            path = write_drpid_aria2_cmd(
                42,
                folder,
                [("big.zip", "https://example.com/big.zip", big)],
                output_dir=out_dir,
            )
            self.assertIsNotNone(path)
            assert path is not None
            self.assertTrue(path.is_file())
            self.assertIn("DRP000042", path.name)
            self.assertIn("aria2c", path.read_text(encoding="utf-8"))
        finally:
            for p in folder.iterdir():
                p.unlink(missing_ok=True)
            folder.rmdir()
            for p in out_dir.glob("DRP000042.cmd"):
                p.unlink(missing_ok=True)
            if out_dir.is_dir() and not any(out_dir.iterdir()):
                out_dir.rmdir()


if __name__ == "__main__":
    unittest.main()
