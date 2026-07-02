"""Tests for ADC large-file size backfill helper."""

from __future__ import annotations

import unittest

from debug.backfill_adc_large_file_sizes import backfill_row, skipped_bytes_from_notes


class TestBackfillAdcLargeFileSizes(unittest.TestCase):
    """Tests for parsing skipped large-file notes."""

    def test_skipped_bytes_from_notes(self) -> None:
        """Skipped download lines contribute bytes and file count."""
        notes = (
            "Skipped download (>1GB): big.zip (5.0 GB) - download manually: http://x\n"
            "Skipped download (>1GB): huge.tar (2.0 GB) - download manually: http://y"
        )
        total, count = skipped_bytes_from_notes(notes)
        self.assertEqual(count, 2)
        self.assertGreaterEqual(total, 7 * 1024**3)

    def test_backfill_row_adds_skipped_totals(self) -> None:
        """Backfill adds skipped bytes and file count to stored values."""
        notes = "Skipped download (>1GB): big.zip (1.5 GB) - download manually: http://x"
        result = backfill_row(1, "200.0 KB", 3, notes)
        self.assertIsNotNone(result)
        new_size, new_files = result
        self.assertEqual(new_files, 4)
        self.assertIn("GB", new_size)


if __name__ == "__main__":
    unittest.main()
