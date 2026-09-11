"""
One-time refresh of File extensions from source catalog pages.

For each project with status ``updated_inventory``, opens the source URL,
surveys top-level download filenames listed on the page (no zip expansion),
updates ``projects.extensions``, and writes the Google Sheet File Extensions
column.

BTS/ROSA P pages require Playwright (plain HTTP is blocked).

From repo root:

    python scripts/refresh_source_file_extensions.py --dry-run
    python scripts/refresh_source_file_extensions.py
    python scripts/refresh_source_file_extensions.py --ids 10,20-25
    python scripts/refresh_source_file_extensions.py -n 5
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import List, Optional, Sequence, Set

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from collectors.BtsMetadataExtractor import (  # noqa: E402
    BtsDownloadFile,
    parse_download_files,
)
from collectors.UsfsPageDownloader import UsfsPageDownloader  # noqa: E402
from storage import Storage  # noqa: E402
from utils.Args import Args  # noqa: E402
from utils.Logger import Logger  # noqa: E402
from utils.drpid_list import parse_drpid_ids  # noqa: E402
from utils.project_utils import get_field  # noqa: E402
from publisher.inventory_sheet_updater import get_inventory_sheet_updater  # noqa: E402

STATUS_UPDATED_INVENTORY = "updated_inventory"


def extensions_from_download_files(files: Sequence[BtsDownloadFile]) -> str:
    """
    Build a sorted comma-separated extension list from catalog download entries.

    Args:
        files: Parsed top-level download file entries from the source page.

    Returns:
        Extension tokens without leading dots, e.g. ``csv, pdf, zip``.
    """
    extensions: Set[str] = set()
    for entry in files:
        name = (entry.filename or "").strip() or entry.url.rsplit("/", 1)[-1]
        suffix = Path(name.split("?")[0]).suffix
        if suffix:
            extensions.add(suffix.lstrip(".").lower())
    return ", ".join(sorted(extensions))


def extensions_from_source_html(html: str, source_url: str) -> str:
    """
    Survey top-level file extensions listed on a BTS/ROSA P detail page.

    Args:
        html: Page HTML.
        source_url: Canonical source URL used to resolve relative links.

    Returns:
        Comma-separated extension tokens from catalog-listed files only.
    """
    return extensions_from_download_files(parse_download_files(html, source_url))


def _select_projects(
    ids: Optional[List[int]],
    num_rows: Optional[int],
) -> List[dict]:
    """Return updated_inventory projects filtered by ids / limit."""
    if ids:
        projects: List[dict] = []
        for drpid in ids:
            project = Storage.get(drpid)
            if not project:
                Logger.warning("DRPID=%s not found in storage; skipping", drpid)
                continue
            status = (project.get("status") or "").strip().lower()
            if status != STATUS_UPDATED_INVENTORY:
                Logger.warning(
                    "DRPID=%s status=%r (expected %s); skipping",
                    drpid,
                    project.get("status"),
                    STATUS_UPDATED_INVENTORY,
                )
                continue
            projects.append(project)
        return projects

    return list(
        Storage.list_eligible_projects(
            STATUS_UPDATED_INVENTORY,
            num_rows,
        )
    )


def refresh_project(
    project: dict,
    page_downloader: UsfsPageDownloader,
    *,
    dry_run: bool,
    update_sheet: bool,
) -> bool:
    """
    Refresh one project's extensions from its source page.

    Returns:
        True on success (including dry-run survey success).
    """
    drpid = int(project["DRPID"])
    source_url = (get_field(project, "source_url") or "").strip()
    if not source_url:
        Logger.error("DRPID=%s missing source_url", drpid)
        return False

    status_code, html, _, _ = page_downloader.fetch_page_html(source_url)
    if status_code != 200 or not html:
        Logger.error(
            "DRPID=%s failed to fetch source page (%s)",
            drpid,
            status_code,
        )
        return False

    extensions = extensions_from_source_html(html, source_url)
    previous = (project.get("extensions") or "").strip()
    Logger.info(
        "DRPID=%s extensions: %r -> %r",
        drpid,
        previous,
        extensions,
    )
    if dry_run:
        return True

    Storage.update_record(drpid, {"extensions": extensions or None})
    if not update_sheet:
        return True

    updater = get_inventory_sheet_updater()
    ok, error = updater.update_file_extensions(source_url, extensions)
    if not ok:
        Logger.error("DRPID=%s sheet update failed: %s", drpid, error)
        return False
    return True


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Refresh File extensions for updated_inventory projects from "
            "source catalog pages (top-level files only; no zip expansion)."
        )
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=REPO_ROOT / "config.json",
        help="Config JSON (default: ./config.json)",
    )
    parser.add_argument(
        "--ids",
        type=str,
        default=None,
        help="Comma-delimited DRPIDs / ranges (e.g. 5,7,10-12)",
    )
    parser.add_argument(
        "-n",
        "--num-rows",
        type=int,
        default=None,
        help="Max projects to process (ignored when --ids is set)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Survey pages and log changes without writing DB or sheet",
    )
    parser.add_argument(
        "--db-only",
        action="store_true",
        help="Update Storage.extensions only; skip Google Sheet write",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run Playwright headed (default headless)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=None,
        help="Seconds between page fetches (default: Args.bts_request_delay)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not args.config.is_file():
        print(f"ERROR: config not found: {args.config}", file=sys.stderr)
        return 1

    Args.initialize_from_config(args.config)
    Logger.initialize(
        log_level=Args.log_level,
        log_color=getattr(Args, "log_color", False),
    )
    Storage.initialize(Args.storage_implementation, db_path=Path(Args.db_path))

    ids = parse_drpid_ids(args.ids) if args.ids else None
    projects = _select_projects(ids, args.num_rows)
    if not projects:
        Logger.info("No updated_inventory projects to process")
        return 0

    delay = (
        float(args.delay)
        if args.delay is not None
        else float(getattr(Args, "bts_request_delay", 0.1) or 0.0)
    )
    page_downloader = UsfsPageDownloader(headless=not args.headed)
    update_sheet = not args.db_only and not args.dry_run
    if update_sheet and (
        not Args.google_sheet_id or not Args.google_credentials
    ):
        print(
            "ERROR: google_sheet_id and google_credentials required "
            "(or pass --db-only / --dry-run).",
            file=sys.stderr,
        )
        return 1

    ok_count = 0
    fail_count = 0
    try:
        for index, project in enumerate(projects):
            if index > 0 and delay > 0:
                time.sleep(delay)
            if refresh_project(
                project,
                page_downloader,
                dry_run=args.dry_run,
                update_sheet=update_sheet,
            ):
                ok_count += 1
            else:
                fail_count += 1
    finally:
        page_downloader.close()

    Logger.info(
        "Finished refresh_source_file_extensions: ok=%s failed=%s dry_run=%s",
        ok_count,
        fail_count,
        args.dry_run,
    )
    return 1 if fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
