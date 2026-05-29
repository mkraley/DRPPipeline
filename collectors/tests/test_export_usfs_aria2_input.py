"""Tests for scripts/export_usfs_aria2_input.py helpers."""

import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "scripts" / "export_usfs_aria2_input.py"


def _load_export_module():
    name = "export_usfs_aria2_input"
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestExportUsfsAria2Input(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_export_module()

    def test_max_connections_for_url(self) -> None:
        self.assertEqual(
            self.mod.max_connections_for_url(
                "https://usfs-public.box.com/shared/static/x.zip"
            ),
            16,
        )
        self.assertEqual(
            self.mod.max_connections_for_url(
                "https://www.fs.usda.gov/rds/archive/products/RDS/x.zip"
            ),
            4,
        )

    def test_entries_for_publication_files_skips_on_disk(self) -> None:
        folder = Path(__file__).parent / "_tmp_aria2_export"
        folder.mkdir(exist_ok=True)
        big = self.mod.MAX_DOWNLOAD_BYTES + 1
        small = 100
        existing = folder / "have.zip"
        existing.write_bytes(b"x" * 10)
        try:
            entries = self.mod.entries_for_publication_files(
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
        entry = self.mod.Aria2Entry(
            url="https://usfs-public.box.com/shared/static/a.zip",
            out_name="big.zip",
            dir_path=Path(r"C:\data\DRP000017"),
            max_connections=16,
        )
        ua = "Mozilla/5.0 Test"
        line = self.mod.format_windows_command(entry, ua)
        self.assertIn("aria2c -c -x 16 -s 16", line)
        self.assertIn('-d "C:\\data\\DRP000017"', line)
        self.assertIn('-o "big.zip"', line)
        self.assertIn("https://usfs-public.box.com/shared/static/a.zip", line)
        self.assertIn('--user-agent="Mozilla/5.0 Test"', line)

    def test_format_windows_commands_batch(self) -> None:
        entry = self.mod.Aria2Entry(
            url="https://example.com/need.zip",
            out_name="need.zip",
            dir_path=Path(r"C:\data\DRP000001"),
            max_connections=8,
        )
        text = self.mod.format_windows_commands([entry], "UA", drpid=1)
        self.assertIn("@echo off", text)
        self.assertIn("REM DRPID 1", text)
        self.assertIn("echo Downloading need.zip", text)
        self.assertIn("if errorlevel 1 exit /b 1", text)


if __name__ == "__main__":
    unittest.main()
