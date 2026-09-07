"""Tests for utils.ChromeRangeDownload."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from utils.ChromeRangeDownload import (
    download_via_chrome_ranges,
    referer_for_file_url,
    requires_chrome_range_download,
)
from utils.Logger import Logger


class TestChromeRangeDownload(unittest.TestCase):
    """Unit tests for Chrome-impersonated Range downloads."""

    @classmethod
    def setUpClass(cls) -> None:
        Logger.initialize(log_level="WARNING")

    def test_requires_chrome_range_download_for_rosap(self) -> None:
        """Only ROSA P hosts need Chrome Range downloads."""
        self.assertTrue(
            requires_chrome_range_download(
                "https://rosap.ntl.bts.gov/view/dot/7547/dot_7547_DS1.zip"
            )
        )
        self.assertFalse(
            requires_chrome_range_download(
                "https://www.fs.usda.gov/rds/archive/products/RDS/x.zip"
            )
        )

    def test_referer_for_file_url(self) -> None:
        """Referer strips the filename from a ROSA P file URL."""
        self.assertEqual(
            referer_for_file_url(
                "https://rosap.ntl.bts.gov/view/dot/7547/dot_7547_DS1.zip"
            ),
            "https://rosap.ntl.bts.gov/view/dot/7547",
        )

    def test_download_via_chrome_ranges_writes_chunks(self) -> None:
        """Chunked Range GETs are appended until Content-Length is reached."""
        total = 10
        chunk_payloads = {
            (0, 3): b"aaaa",
            (4, 7): b"bbbb",
            (8, 9): b"cc",
        }

        class _FakeResponse:
            def __init__(self, status_code: int, headers: dict, body: bytes) -> None:
                self.status_code = status_code
                self.headers = headers
                self._body = body

            def iter_content(self, _size: int):
                yield self._body

            def close(self) -> None:
                return None

        session = MagicMock()
        head = MagicMock()
        head.status_code = 200
        head.headers = {"Content-Length": str(total)}
        session.head.return_value = head

        def _get(_url: str, headers: dict, **_kwargs: object) -> _FakeResponse:
            range_header = headers["Range"]
            start_s, end_s = range_header.replace("bytes=", "").split("-")
            start, end = int(start_s), int(end_s)
            body = chunk_payloads[(start, end)]
            return _FakeResponse(
                206,
                {
                    "Content-Length": str(len(body)),
                    "Content-Range": f"bytes {start}-{end}/{total}",
                },
                body,
            )

        session.get.side_effect = _get

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "file.bin"
            with patch(
                "utils.ChromeRangeDownload._chrome_session", return_value=session
            ):
                size, ok = download_via_chrome_ranges(
                    "https://rosap.ntl.bts.gov/view/dot/1/file.bin",
                    dest,
                    chunk_bytes=4,
                    max_retries=1,
                )
            self.assertTrue(ok)
            self.assertEqual(size, total)
            self.assertEqual(dest.read_bytes(), b"aaaabbbbcc")

    def test_download_via_chrome_ranges_resumes_partial(self) -> None:
        """Existing shorter file is completed from its current offset."""
        total = 8

        class _FakeResponse:
            def __init__(self, body: bytes) -> None:
                self.status_code = 206
                self.headers = {"Content-Length": str(len(body))}
                self._body = body

            def iter_content(self, _size: int):
                yield self._body

            def close(self) -> None:
                return None

        session = MagicMock()
        head = MagicMock()
        head.status_code = 200
        head.headers = {"Content-Length": str(total)}
        session.head.return_value = head
        session.get.return_value = _FakeResponse(b"XXXX")

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "file.bin"
            dest.write_bytes(b"YYYY")
            with patch(
                "utils.ChromeRangeDownload._chrome_session", return_value=session
            ):
                size, ok = download_via_chrome_ranges(
                    "https://rosap.ntl.bts.gov/view/dot/1/file.bin",
                    dest,
                    chunk_bytes=4,
                    max_retries=1,
                )
            self.assertTrue(ok)
            self.assertEqual(size, total)
            self.assertEqual(dest.read_bytes(), b"YYYYXXXX")
            range_header = session.get.call_args.kwargs["headers"]["Range"]
            self.assertEqual(range_header, "bytes=4-7")


if __name__ == "__main__":
    unittest.main()
