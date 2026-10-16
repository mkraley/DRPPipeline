"""Save daily event-notification PDFs and a CSV manifest."""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from scripts.event_notification_links import (
    EventDayLink,
    links_for_month,
    parse_day_links,
    year_index_url,
)
from utils.Logger import Logger

MANIFEST_NAME = "event_notification_manifest.csv"
MANIFEST_COLUMNS = (
    "date",
    "url",
    "relative_path",
    "bytes",
    "sha256",
    "retrieved_at",
    "status",
)


def report_path(dest: Path, link: EventDayLink) -> Path:
    """Return ``dest\\{year}\\{mm}\\{YYYYMMDD}en.pdf``."""
    month_folder = f"{link.day.month:02d}"
    return dest / str(link.day.year) / month_folder / link.filename


def read_manifest(path: Path) -> dict[str, dict[str, str]]:
    """Load manifest rows keyed by ISO date. Missing file yields an empty dict."""
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {row["date"]: row for row in rows if row.get("date")}


def write_manifest(path: Path, rows_by_date: dict[str, dict[str, str]]) -> None:
    """Rewrite the manifest, oldest date first, as UTF-8 with BOM."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = [rows_by_date[key] for key in sorted(rows_by_date)]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(MANIFEST_COLUMNS))
        writer.writeheader()
        writer.writerows(ordered)


def collect_month(
    dest: Path,
    year: int,
    month: int,
    fetch_html: Callable[[str], str],
    save_page: Callable[[str, Path], None],
    delay_seconds: float = 0.0,
    sleeper: Callable[[float], None] | None = None,
) -> dict[str, int]:
    """
    Download one month of daily reports into ``dest`` as PDFs.

    ``fetch_html`` reads the year index. ``save_page`` writes one rendered day.
    Existing non-empty PDFs are left in place and recorded as skipped.
    A failed day is logged and does not stop the rest of the month.

    Returns:
        Counts keyed by ``saved``, ``skipped``, and ``failed``.
    """
    index_html = fetch_html(year_index_url(year))
    links = links_for_month(parse_day_links(index_html), year, month)
    if not links:
        raise ValueError(f"No event notification pages listed for {year}-{month:02d}")
    pause = sleeper or _sleep
    manifest_path = dest / MANIFEST_NAME
    rows = read_manifest(manifest_path)
    counts = {"saved": 0, "skipped": 0, "failed": 0}
    for index, link in enumerate(links):
        if index and delay_seconds > 0:
            pause(delay_seconds)
        row = _collect_day(dest, link, save_page, rows.get(link.day.isoformat()))
        rows[link.day.isoformat()] = row
        counts[row["status"]] += 1
    write_manifest(manifest_path, rows)
    return counts


def _collect_day(
    dest: Path,
    link: EventDayLink,
    save_page: Callable[[str, Path], None],
    existing: dict[str, str] | None,
) -> dict[str, str]:
    """Save one day as a PDF, or reuse the PDF already on disk."""
    path = report_path(dest, link)
    if path.is_file() and path.stat().st_size > 0:
        _remove_html_copy(path)
        return _row_for_file(link, path, dest, "skipped", existing)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        save_page(link.url, path)
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Empty report file for {link.url}")
        _remove_html_copy(path)
    except Exception as exc:
        Logger.error("Could not save %s: %s", link.url, exc)
        _remove_empty(path)
        return _empty_row(link, path, dest)
    return _row_for_file(link, path, dest, "saved", None)


def _row_for_file(
    link: EventDayLink,
    path: Path,
    dest: Path,
    status: str,
    existing: dict[str, str] | None,
) -> dict[str, str]:
    """Build a manifest row from a file on disk."""
    data = path.read_bytes()
    retrieved = (existing or {}).get("retrieved_at") or _utc_now()
    return {
        "date": link.day.isoformat(),
        "url": link.url,
        "relative_path": str(path.relative_to(dest)),
        "bytes": str(len(data)),
        "sha256": hashlib.sha256(data).hexdigest(),
        "retrieved_at": retrieved,
        "status": status,
    }


def _empty_row(link: EventDayLink, path: Path, dest: Path) -> dict[str, str]:
    """Build a manifest row for a day that was not saved."""
    return {
        "date": link.day.isoformat(),
        "url": link.url,
        "relative_path": str(path.relative_to(dest)),
        "bytes": "0",
        "sha256": "",
        "retrieved_at": _utc_now(),
        "status": "failed",
    }


def _remove_html_copy(pdf_path: Path) -> None:
    """Delete an earlier unstyled HTML save that sits beside this PDF."""
    html_path = pdf_path.with_suffix(".html")
    if html_path.is_file():
        html_path.unlink()


def _remove_empty(path: Path) -> None:
    """Delete a zero-byte file left by a failed write."""
    if path.is_file() and path.stat().st_size == 0:
        path.unlink()


def _utc_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sleep(seconds: float) -> None:
    """Pause between page loads."""
    import time

    time.sleep(seconds)
