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

    def test_format_aria2_input(self) -> None:
        entry = self.mod.Aria2Entry(
            url="https://usfs-public.box.com/shared/static/a.zip",
            out_name="big.zip",
            dir_path=Path(r"C:\data\DRP000017"),
            max_connections=16,
        )
        text = self.mod.format_aria2_input([entry])
        self.assertIn("https://usfs-public.box.com/shared/static/a.zip", text)
        self.assertIn("  out=big.zip", text)
        self.assertIn(r"  dir=C:\data\DRP000017", text)
        self.assertIn("  max-connection-per-server=16", text)
        self.assertIn("  split=16", text)


if __name__ == "__main__":
    unittest.main()
