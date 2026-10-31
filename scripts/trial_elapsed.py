"""Elapsed-time helpers for the DataLumos deposit trial."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any


def new_clock() -> dict[str, float]:
    """Return a perf counter with a start mark and a lap mark."""
    now = time.perf_counter()
    return {"start": now, "mark": now}


def lap(clock: dict[str, float], phases: dict[str, int], name: str) -> None:
    """Record milliseconds since the previous lap."""
    now = time.perf_counter()
    phases[name] = int(round((now - clock["mark"]) * 1000))
    clock["mark"] = now


def total_ms(clock: dict[str, float]) -> int:
    """Return milliseconds since the clock started."""
    return int(round((time.perf_counter() - clock["start"]) * 1000))


def format_trial_elapsed(total_ms: int, phases: dict[str, int]) -> str:
    """Format a total duration and the named phases."""
    parts = [f"{name} {_format_ms(value)}" for name, value in phases.items()]
    detail = f" ({', '.join(parts)})" if parts else ""
    return f"Elapsed {_format_ms(total_ms)}{detail}"


def finish_timing(log_path: Path, clock: dict[str, float], phases: dict[str, int]) -> None:
    """Append one summary row so the request log has a total duration."""
    from upload.deposit_page_request import append_deposit_record

    record: dict[str, Any] = {"event": "finished", "elapsedMs": total_ms(clock)}
    for name, value in phases.items():
        record[f"{name}Ms"] = value
    append_deposit_record(log_path, record)


def _format_ms(milliseconds: int) -> str:
    """Format milliseconds as seconds, or minutes and seconds past one minute."""
    seconds = milliseconds / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    remain = seconds - (minutes * 60)
    return f"{minutes}m {remain:.0f}s"
