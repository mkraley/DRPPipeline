"""Tests for collectors.UsfsAria2Export helpers."""

import unittest
from pathlib import Path

from collectors.UsfsAria2Export import (
    Aria2Entry,
    MAX_DOWNLOAD_BYTES,
    aria2_argv_for_download,
    entries_for_publication_files,
    format_windows_command,
    format_windows_commands,
    max_connections_for_url,
    out_name_from_aria2_cmd_line,
    parse_aria2_windows_cmd_line,
    parse_aria2c_lines_from_cmd_text,
    run_aria2_cmd_line_with_retries,
    write_drpid_aria2_cmd,
)
from utils.url_utils import BROWSER_HEADERS


class TestUsfsAria2Export(unittest.TestCase):
    def test_max_connections_for_url(self) -> None:
        self.assertEqual(
            max_connections_for_url("https://usfs-public.box.com/shared/static/x.zip"),
            16,
        )
        self.assertEqual(
            max_connections_for_url("https://www.fs.usda.gov/rds/archive/products/RDS/x.zip"),
            4,
        )

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
