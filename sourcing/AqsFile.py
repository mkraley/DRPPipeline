"""One file belonging to an AirData pre-generated series."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AqsFile:
    """A zip, format page, index, or advisory linked from the download page."""

    filename: str
    rows: int
    size_kb: int
    kind: str
