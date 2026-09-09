"""Tests for utils.ChromeRangeDownload."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from utils.ChromeRangeDownload import (
    ONE_GIB,
    POST_1GIB_CHUNK_BYTES,
    PartialRangeReceived,
    _initial_chunk_size,
    _shrink_chunk_size,
    download_via_chrome_ranges,
    probe_content_length,
    referer_for_file_url,
    requires_chrome_range_download,
)
from utils.Logger import Logger


class _FakeResponse:
    """Minimal curl_cffi-like response for unit tests."""

    def __init__(
        self,
        status_code: int,
        headers: dict[str, str],
        body: bytes = b"",
        *,
        raise_after: int | None = None,
        error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = headers
        self.content = body
        self._body = body
        self._raise_after = raise_after
        self._error = error

    def iter_content(self, _size: int):
        if self._raise_after is not None and self._error is not None:
            yield self._body[: self._raise_after]
            raise self._error
        if self._body:
            yield self._body

    def close(self) -> None:
        return None


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

    def test_chunk_size_shrinks_after_one_gib(self) -> None:
        """Ranges past 1 GiB use the smaller post-1GiB chunk size."""
        self.assertEqual(
            _initial_chunk_size(0, 256 * 1024 * 1024), 256 * 1024 * 1024
        )
        self.assertEqual(
            _initial_chunk_size(ONE_GIB, 256 * 1024 * 1024),
            POST_1GIB_CHUNK_BYTES,
        )
        self.assertEqual(_shrink_chunk_size(4 * 1024 * 1024), 2 * 1024 * 1024)

    def test_probe_content_length_prefers_content_range(self) -> None:
        """Size probe uses Range 0-0 Content-Range when present."""
        session = MagicMock()
        session.get.return_value = _FakeResponse(
            206,
            {"Content-Range": "bytes 0-0/2024010110"},
            b"x",
        )
        size = probe_content_length(
            "https://rosap.ntl.bts.gov/view/dot/1/f.zip",
            session=session,
        )
        self.assertEqual(size, 2024010110)
        session.head.assert_not_called()

    def test_chrome_session_forces_http_1_1(self) -> None:
        """ROSA P sessions must disable HTTP/2 to avoid PROTOCOL_ERROR."""
        from curl_cffi.const import CurlHttpVersion

        with patch("curl_cffi.requests.Session") as mock_session_cls:
            mock_session_cls.return_value = MagicMock()
            from utils.ChromeRangeDownload import _chrome_session

            _chrome_session()
        kwargs = mock_session_cls.call_args.kwargs
        self.assertEqual(kwargs.get("http_version"), CurlHttpVersion.V1_1)

    def test_download_via_chrome_ranges_writes_chunks(self) -> None:
        """Chunked Range GETs are appended until remote size is reached."""
        total = 10
        chunk_payloads = {
            (0, 3): b"aaaa",
            (4, 7): b"bbbb",
            (8, 9): b"cc",
        }

        session = MagicMock()

        def _get(_url: str, headers: dict, **kwargs: object) -> _FakeResponse:
            range_header = headers["Range"]
            if range_header == "bytes=0-0" and not kwargs.get("stream"):
                return _FakeResponse(
                    206, {"Content-Range": f"bytes 0-0/{total}"}, b"x"
                )
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

    def test_small_range_salvages_exception_body(self) -> None:
        """curl 18 with a partial response body is kept as progress."""
        total = 8
        sessions = [MagicMock(), MagicMock()]

        class _Exc(Exception):
            def __init__(self, content: bytes) -> None:
                self.response = MagicMock(content=content)
                super().__init__(
                    "Failed to perform, curl: (18) end of response with 5 bytes missing."
                )

        def _probe_then_fail(_url: str, headers: dict, **kwargs: object):
            range_header = headers["Range"]
            if range_header == "bytes=0-0" and not kwargs.get("stream"):
                return _FakeResponse(
                    206, {"Content-Range": f"bytes 0-0/{total}"}, b"x"
                )
            raise _Exc(b"ABC")

        def _finish(_url: str, headers: dict, **kwargs: object):
            range_header = headers["Range"]
            if range_header == "bytes=0-0" and not kwargs.get("stream"):
                return _FakeResponse(
                    206, {"Content-Range": f"bytes 0-0/{total}"}, b"x"
                )
            start_s, end_s = range_header.replace("bytes=", "").split("-")
            start, end = int(start_s), int(end_s)
            return _FakeResponse(
                206, {"Content-Length": str(end - start + 1)}, b"ABCDEFGH"[start : end + 1]
            )

        sessions[0].get.side_effect = _probe_then_fail
        sessions[1].get.side_effect = _finish

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "file.bin"
            with patch(
                "utils.ChromeRangeDownload._chrome_session",
                side_effect=sessions,
            ), patch("utils.ChromeRangeDownload.time.sleep"):
                size, ok = download_via_chrome_ranges(
                    "https://rosap.ntl.bts.gov/view/dot/1/file.bin",
                    dest,
                    chunk_bytes=8,
                    max_retries=3,
                )
            self.assertTrue(ok)
            self.assertEqual(size, total)
            self.assertEqual(dest.read_bytes(), b"ABCDEFGH")

    def test_download_via_chrome_ranges_resumes_partial(self) -> None:
        """Existing shorter file is completed from its current offset."""
        total = 8
        session = MagicMock()

        def _get(_url: str, headers: dict, **kwargs: object) -> _FakeResponse:
            range_header = headers["Range"]
            if range_header == "bytes=0-0" and not kwargs.get("stream"):
                return _FakeResponse(
                    206, {"Content-Range": f"bytes 0-0/{total}"}, b"x"
                )
            return _FakeResponse(206, {"Content-Length": "4"}, b"XXXX")

        session.get.side_effect = _get

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

    def test_transport_error_recreates_session(self) -> None:
        """Hard failures with no bytes open a fresh session before retrying."""
        total = 4
        sessions = [MagicMock(), MagicMock()]

        def _make_get(succeed_on_stream: bool):
            def _get(_url: str, headers: dict, **kwargs: object) -> _FakeResponse:
                range_header = headers["Range"]
                if range_header == "bytes=0-0" and not kwargs.get("stream"):
                    return _FakeResponse(
                        206, {"Content-Range": f"bytes 0-0/{total}"}, b"x"
                    )
                if kwargs.get("stream") and not succeed_on_stream:
                    raise OSError(
                        "Failed to perform, curl: (92) HTTP/2 stream 1 was not "
                        "closed cleanly: PROTOCOL_ERROR (err 1)."
                    )
                return _FakeResponse(206, {"Content-Length": "4"}, b"data")

            return _get

        sessions[0].get.side_effect = _make_get(False)
        sessions[1].get.side_effect = _make_get(True)

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "file.bin"
            with patch(
                "utils.ChromeRangeDownload._chrome_session",
                side_effect=sessions,
            ), patch("utils.ChromeRangeDownload.time.sleep"):
                size, ok = download_via_chrome_ranges(
                    "https://rosap.ntl.bts.gov/view/dot/1/file.bin",
                    dest,
                    chunk_bytes=4,
                    max_retries=3,
                )
            self.assertTrue(ok)
            self.assertEqual(size, total)
            self.assertEqual(dest.read_bytes(), b"data")
        sessions[0].close.assert_called()


if __name__ == "__main__":
    unittest.main()
