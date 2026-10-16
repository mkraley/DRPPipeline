"""
Save NRC daily event-notification reports as PDF.

Pages are discovered from each year's index. Each PDF is the rendered report
with the site header, menus, and footer hidden. Files already on disk are skipped.
Output defaults to the Reactor Event Notification Report project folder.

From the repo root:

    python scripts/collect_event_notifications.py --year 2026 --month 9
    python scripts/collect_event_notifications.py --year 2024
    python scripts/collect_event_notifications.py --year 1999 --through 2026
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.event_notification_archive import collect_month  # noqa: E402
from scripts.event_notification_browser import EventNotificationBrowser  # noqa: E402
from utils.Logger import Logger  # noqa: E402

DEFAULT_DEST = Path(r"C:\DataRescue\NRCData\NRC000005")
DEFAULT_YEAR = 2026


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser for a month, year, or year range."""
    parser = argparse.ArgumentParser(
        description="Download daily NRC event notification PDFs.",
    )
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR, help="First year")
    parser.add_argument(
        "--through",
        type=int,
        default=None,
        help="Last year, inclusive. Defaults to --year.",
    )
    parser.add_argument(
        "--month",
        type=int,
        default=None,
        help="Month number 1-12. Omit to collect every month.",
    )
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST, help="Project folder")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Seconds to wait between day pages",
    )
    parser.add_argument("--headed", action="store_true", help="Show the browser window")
    return parser


def selected_months(year: int, through: int, month: int | None) -> list[tuple[int, int]]:
    """Return ``(year, month)`` pairs from ``year`` through ``through``."""
    months = [month] if month is not None else list(range(1, 13))
    return [(one_year, one_month) for one_year in range(year, through + 1) for one_month in months]


def collect_months(
    dest: Path,
    pairs: list[tuple[int, int]],
    fetch_html: Callable[[str], str],
    save_page: Callable[[str, Path], None],
    delay_seconds: float = 0.0,
) -> dict[str, int]:
    """
    Download each ``(year, month)`` pair.

    A month with no index links is skipped when more than one month was requested.
    """
    totals = {"saved": 0, "skipped": 0, "failed": 0}
    for year, month in pairs:
        counts = _collect_or_skip(
            dest,
            year,
            month,
            fetch_html,
            save_page,
            delay_seconds,
            len(pairs) == 1,
        )
        for key in totals:
            totals[key] += counts[key]
    return totals


def main(argv: list[str] | None = None) -> int:
    """Download the requested months. Returns 0 when every listed day is on disk."""
    args = build_parser().parse_args(argv)
    through = args.year if args.through is None else args.through
    _validate_args(args.year, through, args.month, args.delay)
    pairs = selected_months(args.year, through, args.month)
    Logger.initialize(log_level="INFO", log_file=False)
    Logger.info("Collecting %s month(s) of event notifications into %s", len(pairs), args.dest)
    with EventNotificationBrowser(headless=not args.headed) as browser:
        counts = collect_months(
            args.dest,
            pairs,
            browser.fetch,
            browser.save_pdf,
            delay_seconds=args.delay,
        )
    Logger.info(
        "Saved %s, skipped %s, failed %s",
        counts["saved"],
        counts["skipped"],
        counts["failed"],
    )
    return 1 if counts["failed"] else 0


def _collect_or_skip(
    dest: Path,
    year: int,
    month: int,
    fetch_html: Callable[[str], str],
    save_page: Callable[[str, Path], None],
    delay_seconds: float,
    only_month: bool,
) -> dict[str, int]:
    """Collect one month, or skip it when a multi-month run has no pages listed."""
    try:
        return collect_month(dest, year, month, fetch_html, save_page, delay_seconds=delay_seconds)
    except ValueError as exc:
        if only_month:
            raise SystemExit(str(exc)) from exc
        Logger.info("%s", exc)
        return {"saved": 0, "skipped": 0, "failed": 0}


def _validate_args(year: int, through: int, month: int | None, delay: float) -> None:
    """Reject a year, month, or delay this collector cannot use."""
    if year < 1999 or through > 2100 or through < year:
        raise SystemExit(f"years must run from 1999 through 2100, got {year}-{through}")
    if month is not None and (month < 1 or month > 12):
        raise SystemExit(f"month must be 1-12, got {month}")
    if delay < 0:
        raise SystemExit(f"delay must be >= 0, got {delay}")


if __name__ == "__main__":
    raise SystemExit(main())
