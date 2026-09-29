"""Tests for aria2 console noise filtering."""

import io
import unittest
from unittest.mock import patch

from collectors.Aria2ConsoleFilter import Aria2ConsoleFilter, forward_aria2_console

_NOISE = (
    "09/29 12:18:15 [ERROR] CUID#8 - Download aborted. URI=https://irma.nps.gov/x\n"
    "Exception: [AbstractCommand.cc:351] errorCode=8 URI=https://irma.nps.gov/x\n"
    "  -> [HttpResponse.cc:81] errorCode=8 Invalid range header. "
    "Request: 1-2/3, Response: 1-2/3\n"
    "[#807d3b 1.6GiB/1.6GiB(99%) CN:1 DL:25MiB]\r"
)
_OTHER_ERROR = (
    "[ERROR] CUID#1 - Download aborted. URI=https://example.com/a\n"
    "Exception: [HttpResponse.cc:81] errorCode=1 URI=https://example.com/a\n"
    "  -> [HttpResponse.cc:81] errorCode=1 timeout\n"
)


class TestAria2ConsoleFilter(unittest.TestCase):
    """Invalid range header blocks are hidden; other console output is kept."""

    def test_drops_invalid_range_block_and_keeps_progress(self) -> None:
        shown = _feed_all(_NOISE)
        self.assertNotIn("Invalid range header", shown)
        self.assertNotIn("Download aborted", shown)
        self.assertIn("[#807d3b", shown)

    def test_keeps_other_download_errors(self) -> None:
        shown = _feed_all(_OTHER_ERROR)
        self.assertIn("errorCode=1 timeout", shown)
        self.assertIn("Download aborted", shown)

    def test_forward_writes_progress_only(self) -> None:
        stream = io.BytesIO(_NOISE.encode("utf-8"))
        with patch("sys.stdout") as stdout:
            forward_aria2_console(stream)
        written = "".join(call.args[0] for call in stdout.write.call_args_list)
        self.assertIn("[#807d3b", written)
        self.assertNotIn("Invalid range header", written)


def _feed_all(text: str) -> str:
    """Feed a console sample one break at a time."""
    console_filter = Aria2ConsoleFilter()
    shown: list[str] = []
    pending = text
    while pending:
        breaks = [index for index in (pending.find("\n"), pending.find("\r")) if index >= 0]
        if not breaks:
            shown.extend(console_filter.feed(pending))
            break
        cut = min(breaks) + 1
        shown.extend(console_filter.feed(pending[:cut]))
        pending = pending[cut:]
    shown.extend(console_filter.flush())
    return "".join(shown)


if __name__ == "__main__":
    unittest.main()
