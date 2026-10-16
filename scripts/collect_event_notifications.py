"""
Save one month of NRC daily event-notification reports as PDF.

Pages are discovered from that year's index. Each PDF is the rendered report
with the site header, menus, and footer hidden. Files already on disk are skipped.
Output defaults to the Reactor Event Notification Report project folder.

From the repo root:

    python scripts/collect_event_notifications.py --year 2026 --month 9
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.event_notification_archive import collect_month  # noqa: E402
from scripts.event_notification_browser import EventNotificationBrowser  # noqa: E402
from utils.Logger import Logger  # noqa: E402

DEFAULT_DEST = Path(r"C:\DataRescue\NRCData\NRC000005")
DEFAULT_YEAR = 2026
DEFAULT_MONTH = 9


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser for a one-month collection."""
    parser = argparse.ArgumentParser(
        description="Download one month of daily NRC event notification PDFs.",
    )
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR, help="Four-digit year")
    parser.add_argument("--month", type=int, default=DEFAULT_MONTH, help="Month number 1-12")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST, help="Project folder")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Seconds to wait between day pages",
    )
    parser.add_argument("--headed", action="store_true", help="Show the browser window")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Download the requested month. Returns 0 when every listed day is on disk."""
    args = build_parser().parse_args(argv)
    _validate_args(args.year, args.month, args.delay)
    Logger.initialize(log_level="INFO", log_file=False)
    Logger.info(
        "Collecting event notifications for %04d-%02d into %s",
        args.year,
        args.month,
        args.dest,
    )
    with EventNotificationBrowser(headless=not args.headed) as browser:
        counts = collect_month(
            args.dest,
            args.year,
            args.month,
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


def _validate_args(year: int, month: int, delay: float) -> None:
    """Reject a year, month, or delay this collector cannot use."""
    if year < 1999 or year > 2100:
        raise SystemExit(f"year must be 1999-2100, got {year}")
    if month < 1 or month > 12:
        raise SystemExit(f"month must be 1-12, got {month}")
    if delay < 0:
        raise SystemExit(f"delay must be >= 0, got {delay}")


if __name__ == "__main__":
    raise SystemExit(main())
