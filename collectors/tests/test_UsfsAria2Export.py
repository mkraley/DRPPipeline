"""Tests for collectors.UsfsAria2Export helpers."""

import unittest
from pathlib import Path

from collectors.UsfsAria2Export import (
    Aria2Entry,
    MAX_DOWNLOAD_BYTES,
    entries_for_publication_files,
    format_windows_command,
    format_windows_commands,
    max_connections_for_url,
    write_drpid_aria2_cmd,
)


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
