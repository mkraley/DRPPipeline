"""Tests for HTTP retry helpers."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import requests

from utils.retry_http import (
    SourceNotFoundError,
    download_with_retry,
    retry_http_call,
)


class TestRetryHttp(unittest.TestCase):
    """Tests for retry_http utilities."""

    def test_retry_http_call_raises_not_found_on_404(self) -> None:
        """404 responses map to SourceNotFoundError without retries."""
        response = MagicMock(status_code=404)
        error = requests.HTTPError("404 Not Found", response=response)

        def _fail() -> None:
            raise error

        with self.assertRaises(SourceNotFoundError):
            retry_http_call(_fail, max_retries=3, base_delay=0)

    @patch("utils.retry_http.time.sleep")
    def test_retry_http_call_retries_403(self, mock_sleep: MagicMock) -> None:
        """403 responses are retried before succeeding."""
        response = MagicMock(status_code=403)
        error = requests.HTTPError("403 Forbidden", response=response)
        calls = {"count": 0}

        def _flaky() -> str:
            calls["count"] += 1
            if calls["count"] == 1:
                raise error
            return "ok"

        result = retry_http_call(_flaky, max_retries=2, base_delay=0)
        self.assertEqual(result, "ok")
        self.assertEqual(calls["count"], 2)

    @patch("utils.retry_http.time.sleep")
    def test_download_with_retry_eventually_succeeds(self, mock_sleep: MagicMock) -> None:
        """Download helper retries until success."""
        attempts = {"count": 0}

        def _download() -> tuple[int, bool]:
            attempts["count"] += 1
            return (0, attempts["count"] >= 2)

        written, success = download_with_retry(
            _download,
            max_retries=2,
            base_delay=0,
        )
        self.assertTrue(success)
        self.assertEqual(attempts["count"], 2)
