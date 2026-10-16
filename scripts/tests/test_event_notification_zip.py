"""Tests for zipping a finished year of event-notification PDFs."""

import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.event_notification_zip import (
    should_zip_year,
    year_is_archived,
    zip_year_folder,
)


class TestEventNotificationZip(unittest.TestCase):
    """A finished year becomes one zip with month folders at the top."""

    def test_should_zip_year_requires_every_month_and_no_failures(self) -> None:
        """One missing month, or any failure, leaves the year unpacked."""
        self.assertTrue(should_zip_year(set(range(1, 13)), 0))
        self.assertFalse(should_zip_year({9}, 0))
        self.assertFalse(should_zip_year(set(range(1, 13)), 1))

    def test_zip_puts_month_folders_at_the_top_and_removes_the_year(self) -> None:
        """The archive matches 2020.zip: ``09/file.pdf``, then the year folder is gone."""
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            september = dest / "2020" / "09"
            september.mkdir(parents=True)
            (september / "20200901en.pdf").write_bytes(b"%PDF-1.4")
            archive = zip_year_folder(dest, 2020)

            self.assertEqual(archive, dest / "2020.zip")
            self.assertFalse((dest / "2020").exists())
            self.assertTrue(year_is_archived(dest, 2020))
            with zipfile.ZipFile(archive) as zipped:
                self.assertEqual(
                    zipped.namelist(),
                    ["09/", "09/20200901en.pdf"],
                )
