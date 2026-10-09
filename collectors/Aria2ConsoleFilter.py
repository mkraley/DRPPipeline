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
        self.error_text = ""

    def feed(self, line: str) -> list[str]:
        """Accept one console piece and return lines that should be shown."""
        if self._pending:
            return self._feed_pending(line)
        if _is_download_aborted_line(line):
            self._pending.append(line)
            return []
        return self._remember([line])

    def flush(self) -> list[str]:
        """Return a held block at end of output, unless it is range noise."""
        if _is_invalid_range_block(self._pending):
            self._pending.clear()
            return []
        return self._remember(self._take_pending())

    def _feed_pending(self, line: str) -> list[str]:
        """Hold an exception continuation, or release the block and this line."""
        if _continues_aria2_exception(line) or not line.strip():
            self._pending.append(line)
            if _is_invalid_range_block(self._pending):
                self._pending.clear()
            return []
        kept = self._take_pending()
        return self._remember(kept) + self.feed(line)

    def _remember(self, lines: list[str]) -> list[str]:
        """Keep shown aria2 errors. Invalid-range blocks never reach here."""
        for line in lines:
            text = line.strip()
            if not _is_shown_aria2_error(text):
                continue
            self.error_text = f"{self.error_text} {text}".strip()
        return lines

    def _take_pending(self) -> list[str]:
        """Return and clear the held lines."""
        kept = self._pending
        self._pending = []
        return kept


def forward_aria2_console(stream: BinaryIO) -> str:
    """Copy aria2 stdout, omitting invalid-range error blocks.

    Returns shown aria2 error text. An empty string means no real error.
    """
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
    return console_filter.error_text


def _emit_complete_pieces(pending: bytes, console_filter: Aria2ConsoleFilter) -> bytes:
    """Print every complete console piece and return the incomplete tail."""
    while True:
        cut = _next_piece_end(pending)
        if cut is None:
            return pending
        piece = pending[:cut].decode("utf-8", errors="replace")
        pending = pending[cut:]
        _write_lines(console_filter.feed(piece))


def _next_piece_end(pending: bytes) -> int | None:
    """Return the end index of the next piece. ``\\r\\n`` stays one piece."""
    carriage = pending.find(b"\r")
    line_feed = pending.find(b"\n")
    if carriage < 0 and line_feed < 0:
        return None
    if line_feed >= 0 and (carriage < 0 or line_feed < carriage):
        return line_feed + 1
    if carriage + 1 == len(pending):
        return None
    if pending[carriage + 1:carriage + 2] == b"\n":
        return carriage + 2
    return carriage + 1


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


def _is_shown_aria2_error(text: str) -> bool:
    """Return True for an emitted line that reports an aria2 failure."""
    return "[ERROR]" in text or text.startswith("Exception:") or text.startswith("->")
