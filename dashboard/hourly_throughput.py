"""Hourly upload and publish completions from ``drp_pipeline.log``.

Counts wall-clock hours, not a sliding window. A finished project is a
failure when an error line was logged for it before the orchestrator
finished that project.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

_HOURS = 48
_CHUNK = 1024 * 1024
_KEYS = ("upload_ok", "upload_fail", "publish_ok", "publish_fail")
_LINE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - (?P<level>[A-Z]+) - "
    r"(?:\[P\d+\] )?(?:\[T\d+\] )?(?:\[(?P<drpid>\d+)\] )?(?P<msg>.*)$"
)
_START = re.compile(r"Orchestrator starting project module='(upload|publish)'")
_FINISH = re.compile(r"Orchestrator finished project module='(upload|publish)'")


def empty_series() -> dict[str, list[int]]:
    """Return four zero lists, one per upload/publish success and failure."""
    return {key: [] for key in _KEYS}


class HourlyThroughput:
    """Incremental reader of upload and publish completions in the pipeline log."""

    def __init__(self, log_path: Path) -> None:
        """
        Args:
            log_path: Path to ``drp_pipeline.log``.
        """
        self._path = log_path
        self._offset = 0
        self._pending = b""
        self._counts: dict[str, dict[str, int]] = {}
        self._open: dict[str, bool] = {}

    def series(self, now: datetime | None = None, hours: int = _HOURS) -> dict[str, object]:
        """
        Return the last ``hours`` wall-clock buckets, including empty hours.

        Args:
            now: Clock used for the window. Defaults to local time.
            hours: Number of hour buckets, ending at the current hour.
        """
        clock = now or datetime.now()
        self._catch_up(clock)
        return self._window(clock, hours)

    def _catch_up(self, now: datetime) -> None:
        """Read newly appended log bytes and fold them into hour buckets."""
        if not self._path.is_file():
            return
        size = self._path.stat().st_size
        if size < self._offset:
            self._reset()
        if self._offset == 0 and size:
            self._offset = self._offset_near(now - timedelta(hours=_HOURS))
        with self._path.open("rb") as handle:
            handle.seek(self._offset)
            data = self._pending + handle.read()
            self._offset = handle.tell()
        self._consume_block(data)

    def _reset(self) -> None:
        """Drop cached counts after the log file shrinks or is replaced."""
        self._offset = 0
        self._pending = b""
        self._counts.clear()
        self._open.clear()

    def _offset_near(self, cutoff: datetime) -> int:
        """Return a file offset at or before the first line near ``cutoff``."""
        size = self._path.stat().st_size
        pos = size
        while pos > 0:
            read_at = max(0, pos - _CHUNK)
            with self._path.open("rb") as handle:
                handle.seek(read_at)
                block = handle.read(pos - read_at)
            first = _first_timestamp(block)
            if read_at == 0 or (first is not None and first <= cutoff):
                return read_at
            pos = read_at
        return 0

    def _consume_block(self, data: bytes) -> None:
        """Parse complete lines and keep a trailing partial line for next time."""
        if not data:
            return
        parts = data.split(b"\n")
        self._pending = parts.pop()
        for raw in parts:
            self._consume_line(raw)

    def _consume_line(self, raw: bytes) -> None:
        """Update open-project state and hour counts from one log line."""
        match = _LINE.match(raw.decode("utf-8", errors="replace"))
        if match is None:
            return
        drpid = match.group("drpid")
        message = match.group("msg")
        if drpid and _START.search(message):
            self._open[drpid] = False
            return
        if drpid and match.group("level") == "ERROR" and drpid in self._open:
            self._open[drpid] = True
            return
        finish = _FINISH.search(message) if drpid else None
        if finish is None or drpid is None:
            return
        failed = self._open.pop(drpid, False)
        kind = "fail" if failed else "ok"
        hour = match.group("ts")[:13] + ":00"
        bucket = self._counts.setdefault(hour, {key: 0 for key in _KEYS})
        bucket[f"{finish.group(1)}_{kind}"] += 1

    def _window(self, now: datetime, hours: int) -> dict[str, object]:
        """Build zero-filled hour labels and series ending at ``now``."""
        end = now.replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(hours=hours - 1)
        labels: list[str] = []
        series = empty_series()
        for step in range(hours):
            stamp = start + timedelta(hours=step)
            labels.append(stamp.strftime("%m-%d %H"))
            bucket = self._counts.get(stamp.strftime("%Y-%m-%d %H:00"), {})
            for key in _KEYS:
                series[key].append(int(bucket.get(key, 0)))
        return {"hours": labels, "series": series, "source": "drp_pipeline.log"}


def _first_timestamp(block: bytes) -> datetime | None:
    """Return the first parseable timestamp in a chunk of log bytes."""
    for raw in block.split(b"\n"):
        match = _LINE.match(raw.decode("utf-8", errors="replace"))
        if match is None:
            continue
        return datetime.strptime(match.group("ts"), "%Y-%m-%d %H:%M:%S")
    return None
