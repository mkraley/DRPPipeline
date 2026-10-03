"""Tests for the shared 1 GiB download budget."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collectors.BudgetedDownload import BudgetedDownload
from collectors.PlannedFile import PlannedFile
from utils.Logger import Logger


class TestBudgetedDownload(unittest.TestCase):
    """Budget stops before a file that would pass 1 GiB."""

    @classmethod
    def setUpClass(cls) -> None:
        """Initialize logging once."""
        Logger.initialize(log_level="WARNING")

    def test_defers_file_that_would_cross_one_gib(self) -> None:
        """The crossing file and everything after it are not downloaded."""
        folder = Path(tempfile.mkdtemp())
        calls: list[str] = []

        def download_one(item: PlannedFile, dest: Path) -> bool:
            calls.append(item.relative_path)
            dest.write_bytes(b"x" * (item.size_bytes or 0))
            return True

        files = [
            PlannedFile("a.bin", "https://example.com/a", 6),
            PlannedFile("b.bin", "https://example.com/b", 6),
            PlannedFile("c.bin", "https://example.com/c", 1),
        ]
        with patch(
            "collectors.BudgetedDownload.would_exceed_download_budget",
            side_effect=lambda downloaded, size: size is None or downloaded + size > 10,
        ), patch(
            "collectors.BudgetedDownload.download_budget_exhausted",
            side_effect=lambda downloaded: downloaded >= 10,
        ):
            outcome = BudgetedDownload().download_until_budget(1, folder, files, download_one)
        self.assertEqual(calls, ["a.bin"])
        self.assertTrue(outcome.deferred)
        self.assertTrue(any("b.bin" in note for note in outcome.notes))
        self.assertTrue(any("c.bin" in note for note in outcome.notes))

    def test_sidecar_bytes_do_not_spend_the_budget(self) -> None:
        """A generated metadata file already on disk does not defer data files."""
        folder = Path(tempfile.mkdtemp())
        (folder / "project_metadata.json").write_bytes(b"x" * 20)
        seen: list[str] = []

        def download_one(item: PlannedFile, dest: Path) -> bool:
            seen.append(item.relative_path)
            dest.write_bytes(b"ok")
            return True

        files = [PlannedFile("data.bin", "https://example.com/data", 100)]
        outcome = BudgetedDownload().download_until_budget(1, folder, files, download_one)
        self.assertEqual(seen, ["data.bin"])
        self.assertFalse(outcome.deferred)

    def test_unknown_size_is_deferred(self) -> None:
        """A file with no catalog size is not started."""
        folder = Path(tempfile.mkdtemp())

        def download_one(item: PlannedFile, dest: Path) -> bool:
            dest.write_bytes(b"no")
            return True

        files = [PlannedFile("mystery.bin", "https://example.com/m", None)]
        outcome = BudgetedDownload().download_until_budget(1, folder, files, download_one)
        self.assertTrue(outcome.deferred)
        self.assertFalse((folder / "mystery.bin").exists())

    def test_write_sidecars_runs_after_the_budget_stops(self) -> None:
        """Sidecars are written even when data files were deferred."""
        folder = Path(tempfile.mkdtemp())
        wrote: list[str] = []
        files = [PlannedFile("big.bin", "https://example.com/big", 10**12)]
        BudgetedDownload().download_until_budget(
            1,
            folder,
            files,
            lambda _item, _dest: False,
            write_sidecars=lambda: wrote.append("yes"),
        )
        self.assertEqual(wrote, ["yes"])
