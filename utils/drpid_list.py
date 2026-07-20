"""
Parse DRPID list specs for the ``--ids`` CLI option.

Supports comma-separated IDs and inclusive ranges, e.g. ``5,7,10-12`` →
``[5, 7, 10, 11, 12]``.
"""

from __future__ import annotations

from typing import List


def parse_drpid_ids(spec: str) -> List[int]:
    """
    Parse a comma-delimited DRPID list that may include ranges.

    Args:
        spec: e.g. ``"5"``, ``"1,3,5"``, ``"5-7"``, ``"1,3,5-8,20"``.

    Returns:
        Sorted unique DRPIDs in ascending order.

    Raises:
        ValueError: If the spec is empty or contains an invalid token/range.
    """
    text = (spec or "").strip()
    if not text:
        raise ValueError("--ids requires a non-empty comma-delimited list of DRPIDs")

    found: set[int] = set()
    for raw_part in text.split(","):
        part = raw_part.strip()
        if not part:
            raise ValueError(f"Invalid empty token in --ids: {spec!r}")
        if "-" in part:
            found.update(_parse_range(part, spec))
        else:
            found.add(_parse_single(part, spec))
    return sorted(found)


def _parse_single(token: str, spec: str) -> int:
    """Parse one integer DRPID token."""
    try:
        value = int(token)
    except ValueError as exc:
        raise ValueError(f"Invalid DRPID {token!r} in --ids {spec!r}") from exc
    if value < 1:
        raise ValueError(f"DRPID must be >= 1, got {value} in --ids {spec!r}")
    return value


def _parse_range(token: str, spec: str) -> List[int]:
    """Parse an inclusive ``start-end`` range token."""
    pieces = token.split("-", 1)
    if len(pieces) != 2 or not pieces[0].strip() or not pieces[1].strip():
        raise ValueError(f"Invalid DRPID range {token!r} in --ids {spec!r}")
    start = _parse_single(pieces[0].strip(), spec)
    end = _parse_single(pieces[1].strip(), spec)
    if end < start:
        raise ValueError(
            f"Invalid DRPID range {token!r} in --ids {spec!r}: end < start"
        )
    return list(range(start, end + 1))
