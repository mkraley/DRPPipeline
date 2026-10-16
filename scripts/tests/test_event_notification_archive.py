"""Tests for saving one month of event-notification PDFs."""

import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from scripts.event_notification_archive import MANIFEST_NAME, collect_month, read_manifest
from scripts.event_notification_links import looks_like_event_report
from utils.Logger import Logger

_INDEX = """
<html><body>
<a href="/documents-reports/document-collections/events-reports-associated-with/event-notification-reports/2026/20260901en">Sep 1</a>
<a href="/documents-reports/document-collections/events-reports-associated-with/event-notification-reports/2026/20260902en">Sep 2</a>
<a href="/documents-reports/document-collections/events-reports-associated-with/event-notification-reports/2026/20261001en">Oct 1</a>
</body></html>
"""


class TestCollectEventNotificationMonth(unittest.TestCase):
    """collect_month writes the requested month and skips files already saved."""

    def setUp(self) -> None:
        """Logger is required when a day fails."""
        Logger.initialize(log_level="ERROR", log_file=False)

    def test_saves_pdfs_and_skips_on_second_run(self) -> None:
        """The second pass records skipped and keeps the first retrieval time."""
        pages = {
            "20260901en": b"%PDF Event Notification Report one",
            "20260902en": b"%PDF Event Notification Report two",
        }
        with self._temp_dest() as dest:
            first = collect_month(dest, 2026, 9, self._index, self._saver(pages), delay_seconds=0)
            retrieved = read_manifest(dest / MANIFEST_NAME)["2026-09-01"]["retrieved_at"]
            second = collect_month(dest, 2026, 9, self._index, self._saver(pages), delay_seconds=0)
            again = read_manifest(dest / MANIFEST_NAME)["2026-09-01"]
            self.assertTrue((dest / "2026" / "20260901en.pdf").is_file())
        self.assertEqual(first, {"saved": 2, "skipped": 0, "failed": 0})
        self.assertEqual(second, {"saved": 0, "skipped": 2, "failed": 0})
        self.assertEqual(again["retrieved_at"], retrieved)
        self.assertEqual(again["status"], "skipped")

    def test_failed_day_does_not_stop_the_month(self) -> None:
        """An access-denied page is recorded as failed and is not written."""
        pages = {
            "20260901en": b"Access Denied edgesuite",
            "20260902en": b"%PDF Event Notification Report two",
        }
        with self._temp_dest() as dest:
            counts = collect_month(dest, 2026, 9, self._index, self._saver(pages))
            saved = dest / "2026" / "20260902en.pdf"
            blocked = dest / "2026" / "20260901en.pdf"
            self.assertTrue(saved.is_file())
            self.assertFalse(blocked.exists())
            manifest = read_manifest(dest / MANIFEST_NAME)
        self.assertEqual(counts, {"saved": 1, "skipped": 0, "failed": 1})
        self.assertEqual(manifest["2026-09-01"]["status"], "failed")
        self.assertEqual(manifest["2026-09-02"]["status"], "saved")

    def test_replaces_unstyled_html_with_pdf(self) -> None:
        """A leftover HTML file beside the PDF is removed after a successful save."""
        pages = {
            "20260901en": b"%PDF Event Notification Report one",
            "20260902en": b"%PDF Event Notification Report two",
        }
        with self._temp_dest() as dest:
            html_copy = dest / "2026" / "20260901en.html"
            html_copy.parent.mkdir(parents=True)
            html_copy.write_text("<html>unstyled</html>", encoding="utf-8")
            collect_month(dest, 2026, 9, self._index, self._saver(pages))
            self.assertFalse(html_copy.exists())
            self.assertTrue((dest / "2026" / "20260901en.pdf").is_file())

    def test_empty_month_raises(self) -> None:
        """A month with no index links is an error."""
        with self._temp_dest() as dest:
            with self.assertRaises(ValueError):
                collect_month(dest, 2026, 8, self._index, self._saver({}))

    def _index(self, url: str) -> str:
        """Return the fixed year index."""
        if not url.endswith("/index"):
            raise AssertionError(url)
        return _INDEX

    def _saver(self, pages: dict[str, bytes]):
        """Return a save function that writes stand-in PDF bytes or rejects a block page."""

        def save(url: str, path: Path) -> None:
            for stamp, body in pages.items():
                if stamp not in url:
                    continue
                text = body.decode("utf-8")
                if not looks_like_event_report(text) and not text.startswith("%PDF"):
                    raise RuntimeError(f"Page is not an event notification report: {url}")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
                return
            raise AssertionError(url)

        return save

    @contextmanager
    def _temp_dest(self):
        """Create a temporary project folder."""
        with tempfile.TemporaryDirectory() as tmp:
            yield Path(tmp)
