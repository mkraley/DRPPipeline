"""Summarize and histogram file_size values from adc.db."""

from __future__ import annotations

import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.file_utils import format_file_size, parse_file_size_to_bytes

# Histogram bucket upper bounds in bytes (inclusive labels).
BUCKET_BOUNDS = [
    (1024, "<= 1 KB"),
    (1024**2, "<= 1 MB"),
    (10 * 1024**2, "<= 10 MB"),
    (100 * 1024**2, "<= 100 MB"),
    (1024**3, "<= 1 GB"),
    (10 * 1024**3, "<= 10 GB"),
    (100 * 1024**3, "<= 100 GB"),
    (float("inf"), "> 100 GB"),
]


def bucket_label(size_bytes: int) -> str:
    """Return the histogram bucket label for a byte count."""
    for upper, label in BUCKET_BOUNDS:
        if size_bytes <= upper:
            return label
    return "> 100 GB"


def summarize(db_path: Path) -> None:
    """
    Print total file_size and a text histogram for all projects.

    Args:
        db_path: Path to adc.db (or copy).
    """
    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        "SELECT DRPID, status, file_size FROM projects ORDER BY DRPID",
    ).fetchall()
    connection.close()

    parsed: list[tuple[int, str, int]] = []
    missing = 0
    unparseable: list[tuple[int, str]] = []
    for drpid, status, file_size in rows:
        bytes_val = parse_file_size_to_bytes(file_size)
        if bytes_val is None:
            if file_size is None or str(file_size).strip() == "":
                missing += 1
            else:
                unparseable.append((drpid, str(file_size)))
            continue
        parsed.append((drpid, status, bytes_val))

    total_bytes = sum(item[2] for item in parsed)
    bucket_counts = Counter(bucket_label(size) for _, _, size in parsed)
    labels = [label for _, label in BUCKET_BOUNDS]
    max_count = max(bucket_counts.values()) if bucket_counts else 1
    bar_width = 40

    print(f"Database: {db_path}")
    print(f"Projects: {len(rows)}")
    print(f"With parseable file_size: {len(parsed)}")
    print(f"Missing/empty file_size: {missing}")
    print(f"Unparseable file_size: {len(unparseable)}")
    print()
    print(f"Total file_size: {format_file_size(total_bytes)} ({total_bytes:,} bytes)")
    print(f"Mean (parseable rows): {format_file_size(total_bytes // len(parsed) if parsed else 0)}")
    print()
    print("Histogram (by project file_size):")
    for label in labels:
        count = bucket_counts.get(label, 0)
        bar_len = int(round(count / max_count * bar_width)) if max_count else 0
        bar = "#" * bar_len
        pct = 100.0 * count / len(parsed) if parsed else 0.0
        print(f"  {label:>12}  {count:4d}  ({pct:5.1f}%)  {bar}")

    if unparseable:
        print()
        print("Unparseable samples (first 10):")
        for drpid, raw in unparseable[:10]:
            print(f"  DRPID {drpid}: {raw!r}")


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "adc.db"
    summarize(path)
