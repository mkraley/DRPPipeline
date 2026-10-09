"""Tests for scripts.zip_deferred_uploads."""

import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.zip_deferred_uploads import (
    collect_folder_files,
    group_skip_files,
    write_stored_zip,
    zip_output_path,
)


class TestZipDeferredUploads(unittest.TestCase):
    """Skip-note files are zipped one product folder at a time."""

    def test_group_skip_files_keeps_folder_membership(self) -> None:
        """Files from different product folders stay in separate groups."""
        notes = (
            "Skipped download (>1GB): a.zip (1.1 GB) in Birds_2020 - "
            "download manually: https://irma.nps.gov/a\n"
            "Skipped download (>1GB): b.zip (2.0 GB) in Birds_2020 - "
            "download manually: https://irma.nps.gov/b\n"
            "Skipped download (>1GB): c.zip (3.0 GB) in Birds_2019 - "
            "download manually: https://irma.nps.gov/c\n"
        )
        grouped = group_skip_files(notes)
        self.assertEqual(grouped["Birds_2020"], ["a.zip", "b.zip"])
        self.assertEqual(grouped["Birds_2019"], ["c.zip"])

    def test_write_stored_zip_uses_project_relative_paths(self) -> None:
        """One folder's deferred files share a zip under that folder name."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "Birds_2020"
            folder.mkdir()
            (folder / "a.zip").write_bytes(b"aaa")
            (folder / "b.zip").write_bytes(b"bbbb")
            (folder / "product_metadata.json").write_text("{}", encoding="utf-8")
            paths = collect_folder_files(root, "Birds_2020", ["a.zip", "b.zip"])
            dest = root / "out" / "Birds_2020.zip"
            write_stored_zip(root, paths, dest)
            with zipfile.ZipFile(dest) as archive:
                self.assertEqual(
                    archive.namelist(),
                    ["Birds_2020/a.zip", "Birds_2020/b.zip"],
                )
                self.assertEqual(archive.getinfo("Birds_2020/a.zip").compress_type, zipfile.ZIP_STORED)

    def test_missing_file_does_not_resolve(self) -> None:
        """A skip-note name that is not on disk is reported before zipping."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Birds_2020").mkdir()
            with self.assertRaises(FileNotFoundError):
                collect_folder_files(root, "Birds_2020", ["gone.zip"])

    def test_zip_output_path_uses_project_prefix(self) -> None:
        """Archives land in a per-project directory named for the folder."""
        dest = zip_output_path(Path(r"C:\zips"), 429, "Birds_2020", prefix="NPS")
        self.assertEqual(dest, Path(r"C:\zips\NPS000429\Birds_2020.zip"))


if __name__ == "__main__":
    unittest.main()
