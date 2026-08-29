"""
Unit tests for batch download API helpers.
"""

import unittest
from unittest.mock import MagicMock, patch

from interactive_collector.api_batch_download import (
    control_batch_download,
    generate_batch_download_progress,
    resolve_batch_urls,
)
from interactive_collector.batch_download_state import create_batch_download_job


class TestResolveBatchUrls(unittest.TestCase):
    """Tests for resolve_batch_urls."""

    @patch("interactive_collector.api_batch_download.get_scoreboard_urls", return_value=[])
    @patch(
        "interactive_collector.api_batch_download.preview_data_links_from_page_url",
        return_value=(["https://x.com/a.pdf"], None),
    )
    def test_from_page_url(self, _mock_preview: MagicMock, _mock_sb: MagicMock) -> None:
        """Resolves links by fetching page when urls not provided."""
        urls, err = resolve_batch_urls("https://catalog.example.com/", None, True)
        self.assertIsNone(err)
        self.assertEqual(urls, ["https://x.com/a.pdf"])

    @patch("interactive_collector.api_batch_download.get_scoreboard_urls", return_value=["https://x.com/a.pdf"])
    def test_skip_existing(self, _mock_sb: MagicMock) -> None:
        """skip_existing removes scoreboard URLs."""
        urls, err = resolve_batch_urls(
            None,
            ["https://x.com/a.pdf", "https://x.com/b.csv"],
            True,
        )
        self.assertIsNone(err)
        self.assertEqual(urls, ["https://x.com/b.csv"])


class TestGenerateBatchDownloadProgress(unittest.TestCase):
    """Tests for generate_batch_download_progress streaming."""

    @patch("interactive_collector.api_batch_download.generate_download_progress")
    def test_yields_job_and_done(self, mock_one: MagicMock) -> None:
        """Stream includes JOB id and BATCH_DONE."""
        mock_one.return_value = iter(["SAVING\tf.pdf\n", "DONE\tf.pdf\t10\tpdf\n"])
        lines = list(
            generate_batch_download_progress(
                ["https://example.com/f.pdf"],
                "C:\\out",
                1,
                "https://ref.example.com",
                delay_sec=0,
            )
        )
        self.assertTrue(any(l.startswith("JOB\t") for l in lines))
        self.assertTrue(any(l.startswith("BATCH_DONE\t") for l in lines))
        mock_one.assert_called_once()

    @patch("interactive_collector.api_batch_download.generate_download_progress")
    def test_cancel_stops_batch(self, mock_one: MagicMock) -> None:
        """Cancelled job emits CANCELLED before second file."""
        mock_one.return_value = iter(["SAVING\ta.pdf\n", "DONE\ta.pdf\t1\tpdf\n"])
        job = create_batch_download_job()
        gen = generate_batch_download_progress(
            ["https://example.com/a.pdf", "https://example.com/b.pdf"],
            "C:\\out",
            1,
            None,
            delay_sec=0,
            job=job,
        )
        for line in gen:
            if line.startswith("DONE\t"):
                job.cancelled = True
                break
        rest = list(gen)
        self.assertTrue(any("CANCELLED" in l for l in rest))
        self.assertEqual(mock_one.call_count, 1)


class TestControlBatchDownload(unittest.TestCase):
    """Tests for pause/resume/cancel control."""

    def test_pause_resume(self) -> None:
        """Pause and resume toggle job flags."""
        job = create_batch_download_job()
        self.assertTrue(control_batch_download(job.job_id, "pause")[0])
        self.assertTrue(job.paused)
        self.assertTrue(control_batch_download(job.job_id, "resume")[0])
        self.assertFalse(job.paused)


if __name__ == "__main__":
    unittest.main()
