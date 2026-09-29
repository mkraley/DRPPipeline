"""Filter aria2 console output that does not indicate a failed download."""

from __future__ import annotations

import sys
from typing import BinaryIO


class Aria2ConsoleFilter:
    """
    Pass aria2 console output through, dropping invalid-range blocks.

    IRMA answers a byte-range request with the rest of the file. aria2 logs
    errorCode 8 ``Invalid range header`` and keeps downloading. Those blocks
    are noise. Other errors are printed.
    """

    def __init__(self) -> None:
        """Start with no held error block."""
        self._pending: list[str] = []

    def feed(self, line: str) -> list[str]:
        """Accept one console piece and return lines that should be shown."""
        if self._pending:
            return self._feed_pending(line)
        if _is_download_aborted_line(line):
            self._pending.append(line)
            return []
        return [line]

    def flush(self) -> list[str]:
        """Return a held block at end of output, unless it is range noise."""
        if _is_invalid_range_block(self._pending):
            self._pending.clear()
            return []
        return self._take_pending()

    def _feed_pending(self, line: str) -> list[str]:
        """Hold an exception continuation, or release the block and this line."""
        if _continues_aria2_exception(line):
            self._pending.append(line)
            if _is_invalid_range_block(self._pending):
                self._pending.clear()
            return []
        kept = self._take_pending()
        return kept + self.feed(line)

    def _take_pending(self) -> list[str]:
        """Return and clear the held lines."""
        kept = self._pending
        self._pending = []
        return kept


def forward_aria2_console(stream: BinaryIO) -> None:
    """Copy aria2 stdout, omitting invalid-range error blocks."""
    console_filter = Aria2ConsoleFilter()
    pending = b""
    while True:
        chunk = stream.read(4096)
        if not chunk:
            break
        pending += chunk
        pending = _emit_complete_pieces(pending, console_filter)
    if pending:
        _write_lines(console_filter.feed(pending.decode("utf-8", errors="replace")))
    _write_lines(console_filter.flush())


def _emit_complete_pieces(pending: bytes, console_filter: Aria2ConsoleFilter) -> bytes:
    """Print every \\n or \\r piece and return the incomplete tail."""
    while True:
        indexes = [index for index in (pending.find(b"\n"), pending.find(b"\r")) if index >= 0]
        if not indexes:
            return pending
        cut = min(indexes) + 1
        piece = pending[:cut].decode("utf-8", errors="replace")
        pending = pending[cut:]
        _write_lines(console_filter.feed(piece))


def _write_lines(lines: list[str]) -> None:
    """Write console lines immediately so the progress readout stays live."""
    for line in lines:
        sys.stdout.write(line)
        sys.stdout.flush()


def _is_download_aborted_line(line: str) -> bool:
    """Return True for the first line of an aria2 per-connection error."""
    return "[ERROR]" in line and "Download aborted" in line


def _continues_aria2_exception(line: str) -> bool:
    """Return True for the exception lines that follow Download aborted."""
    text = line.lstrip()
    return text.startswith("Exception:") or text.startswith("->")


def _is_invalid_range_block(lines: list[str]) -> bool:
    """Return True when a held block is the IRMA range-header mismatch."""
    return any("Invalid range header" in line for line in lines)
