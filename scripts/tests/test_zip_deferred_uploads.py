"""Tests for scripts.zip_deferred_uploads."""

import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.DeferredZipParts import (
    catalog_files,
    pack_by_max_size,
    part_suffix,
    plan_zip_parts,
    write_stored_zip,
)
from scripts.zip_deferred_uploads import (
    collect_folder_files,
    collect_project_files,
    group_skip_files,
    zip_output_path,
)


class TestZipDeferredUploads(unittest.TestCase):
    """The first zip holds folders and catalog files; later zips hold content."""

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

    def test_write_stored_zip_keeps_product_folders_in_one_archive(self) -> None:
        """Deferred files from every product folder share one project zip."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            later = root / "Birds_2019"
            earlier = root / "Birds_2020"
            later.mkdir()
            earlier.mkdir()
            (earlier / "a.zip").write_bytes(b"aaa")
            (earlier / "product_metadata.json").write_text("{}", encoding="utf-8")
            (later / "c.zip").write_bytes(b"ccc")
            grouped = {"Birds_2020": ["a.zip"], "Birds_2019": ["c.zip"]}
            paths = collect_project_files(root, grouped)
            dest = root / "out" / "NPS000429.zip"
            write_stored_zip(root, paths, dest)
            with zipfile.ZipFile(dest) as archive:
                self.assertEqual(
                    archive.namelist(),
                    ["Birds_2020/a.zip", "Birds_2019/c.zip"],
                )
                info = archive.getinfo("Birds_2020/a.zip")
                self.assertEqual(info.compress_type, zipfile.ZIP_STORED)

    def test_missing_file_does_not_resolve(self) -> None:
        """A skip-note name that is not on disk is reported before zipping."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Birds_2020").mkdir()
            with self.assertRaises(FileNotFoundError):
                collect_folder_files(root, "Birds_2020", ["gone.zip"])

    def test_zip_output_path_is_one_file_per_project(self) -> None:
        """Without a size limit, each project is a single archive."""
        dest = zip_output_path(Path(r"C:\zips"), 429, prefix="NPS")
        self.assertEqual(dest, Path(r"C:\zips\NPS000429.zip"))

    def test_size_limit_names_parts_with_letters(self) -> None:
        """Split archives are named with the DRPID and a letter."""
        self.assertEqual(part_suffix(0), "a")
        self.assertEqual(part_suffix(1), "b")
        self.assertEqual(part_suffix(25), "z")
        first = zip_output_path(Path(r"C:\zips"), 429, prefix="NPS", part_index=0)
        second = zip_output_path(Path(r"C:\zips"), 429, prefix="NPS", part_index=1)
        self.assertEqual(first, Path(r"C:\zips\429a.zip"))
        self.assertEqual(second, Path(r"C:\zips\429b.zip"))

    def test_pack_by_max_size_fills_each_zip_in_order(self) -> None:
        """82 bytes with a 20-byte limit becomes five groups."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = []
            for index in range(4):
                path = root / f"chunk{index}.bin"
                path.write_bytes(b"x" * 20)
                paths.append(path)
            tail = root / "tail.bin"
            tail.write_bytes(b"x" * 2)
            paths.append(tail)
            groups = pack_by_max_size(paths, 20)
        self.assertEqual(len(groups), 5)
        self.assertEqual(groups[-1], [tail])

    def test_first_zip_is_folders_and_catalog_then_content_is_split(self) -> None:
        """Catalog files stay in the first zip. Content starts in the next ones."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            birds = root / "Birds_2020"
            birds.mkdir()
            (birds / "product_metadata.json").write_text("{}", encoding="utf-8")
            (root / "project_metadata.json").write_text("{}", encoding="utf-8")
            big = birds / "a.zip"
            later = birds / "b.zip"
            big.write_bytes(b"a" * 30)
            later.write_bytes(b"b" * 30)
            parts = plan_zip_parts(root, [big, later], max_bytes=40)
            self.assertEqual(len(parts), 3)
            directories, catalogs = parts[0]
            self.assertEqual(directories, ["Birds_2020"])
            self.assertEqual(catalogs, catalog_files(root))
            self.assertEqual(parts[1][1], [big])
            self.assertEqual(parts[2][1], [later])
            dest = root / "out" / "429a.zip"
            write_stored_zip(root, catalogs, dest, directories)
            with zipfile.ZipFile(dest) as archive:
                self.assertIn("Birds_2020/", archive.namelist())
                self.assertIn("Birds_2020/product_metadata.json", archive.namelist())
                self.assertNotIn("Birds_2020/a.zip", archive.namelist())


if __name__ == "__main__":
    unittest.main()
