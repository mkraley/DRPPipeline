"""Tests for IRMA aria2 command export."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from collectors.NpsAria2Export import write_nps_aria2_cmd
from collectors.NpsDownloadPlan import NpsPlannedFile
from collectors.UsfsAria2Export import aria2_cmd_download_parts, parse_aria2c_lines_from_cmd_file


class TestNpsAria2Export(unittest.TestCase):
    """Aria2 commands for missing IRMA files use the product folder."""

    def test_command_targets_product_subfolder(self) -> None:
        """``-d`` is the product folder and the line includes the IRMA referer."""
        entry = NpsPlannedFile(
            url="https://irma.nps.gov/DataStore/DownloadFile/9",
            filename="later.zip",
            relative_dir="Later_tables",
            size_bytes=1024,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "NPS000321"
            out_dir = root / "aria2_inputs"
            cmd_path = write_nps_aria2_cmd(321, project, [entry], output_dir=out_dir)
            self.assertIsNotNone(cmd_path)
            assert cmd_path is not None
            lines = parse_aria2c_lines_from_cmd_file(cmd_path)
            url, dest_dir, out_name = aria2_cmd_download_parts(lines[0])
            self.assertEqual(out_name, "later.zip")
            self.assertEqual(url, entry.url)
            self.assertEqual(dest_dir, (project / "Later_tables").resolve())
            self.assertIn("--referer=https://irma.nps.gov/", lines[0])

    def test_skips_files_already_on_disk(self) -> None:
        """A file already in its product folder is left out of the command file."""
        entry = NpsPlannedFile(
            url="https://irma.nps.gov/DataStore/DownloadFile/1",
            filename="have.zip",
            relative_dir="Product",
            size_bytes=10,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / "Product"
            dest.mkdir()
            (dest / "have.zip").write_bytes(b"x")
            cmd_path = write_nps_aria2_cmd(1, root, [entry], output_dir=root / "out")
            self.assertIsNone(cmd_path)
