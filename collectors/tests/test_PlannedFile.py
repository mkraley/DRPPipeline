"""Tests for planned-file inventory totals."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from collectors.PlannedFile import PlannedFile, inventory_with_deferred


class TestInventoryWithDeferred(unittest.TestCase):
    """Deferred downloads count toward file_size and num_files."""

    def test_deferred_size_is_included_and_refused_files_are_not(self) -> None:
        """A skipped large file adds its size. An unsupported format does not."""
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "saved.csv").write_bytes(b"12345")
            extensions, total_bytes, num_files = inventory_with_deferred(
                folder,
                [
                    PlannedFile("saved.csv", "https://example.com/saved.csv", 5),
                    PlannedFile("big.zip", "https://example.com/big.zip", 1000),
                    PlannedFile(
                        "nope.sqlite",
                        "https://example.com/nope.sqlite",
                        access_error="unsupported file format",
                    ),
                ],
            )
        self.assertEqual(num_files, 2)
        self.assertEqual(total_bytes, 1005)
        self.assertEqual(extensions, ["csv", "zip"])

    def test_on_disk_file_is_not_counted_twice(self) -> None:
        """A planned file already saved uses its on-disk size once."""
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "saved.csv").write_bytes(b"1234567890")
            _extensions, total_bytes, num_files = inventory_with_deferred(
                folder,
                [PlannedFile("saved.csv", "https://example.com/saved.csv", 3)],
            )
        self.assertEqual(num_files, 1)
        self.assertEqual(total_bytes, 10)


if __name__ == "__main__":
    unittest.main()
