"""
Infer and backfill data_types for USFS projects from title, abstract, and FGDC metadata.

Values are stored semicolon-delimited in the projects table (DataLumos kindOfData labels).
Records with insufficient confidence get an empty data_types field.

Run from repo root:
    python scripts/infer_usfs_data_types.py
    python scripts/infer_usfs_data_types.py --db-path usfs.db --limit 20
    python scripts/infer_usfs_data_types.py --only-empty
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from collectors.UsfsMetadataExtractor import (  # noqa: E402
    infer_data_types,
    metadata_url_for_rds_id,
    rds_id_from_source_url,
)
from utils.Logger import Logger  # noqa: E402
from utils.url_utils import PlaywrightFetchSession, fetch_page_body  # noqa: E402

DEFAULT_DB_PATH = REPO_ROOT / "usfs.db"


def _fetch_metadata_html(
    url: str,
    *,
    browser_session: PlaywrightFetchSession | None,
    use_browser_only: bool,
) -> tuple[int, str, PlaywrightFetchSession | None]:
    """Fetch metadata HTML, reusing a Playwright session when HTTP fails."""
    if browser_session is not None:
        status, html, _, _ = browser_session.fetch_page_body(url)
        return status, html, browser_session

    if not use_browser_only:
        status, html, _, _ = fetch_page_body(url)
        if status == 200 and html:
            return status, html, None
        Logger.warning(
            "HTTP fetch failed (status=%s) for %s; switching to Playwright browser session",
            status,
            url,
        )
    else:
        Logger.info("Using Playwright browser session (--browser)")

    browser_session = PlaywrightFetchSession(timeout=60)
    browser_session.__enter__()
    status, html, _, _ = browser_session.fetch_page_body(url)
    return status, html, browser_session


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill USFS data_types in DB")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--limit", type=int, default=0, help="Max records (0 = all)")
    parser.add_argument("--delay", type=float, default=0.15, help="Seconds between HTTP requests")
    parser.add_argument(
        "--only-empty",
        action="store_true",
        help="Update only rows where data_types is NULL or empty",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Fetch metadata with Playwright only (recommended when requests SSL fails)",
    )
    args = parser.parse_args()

    Logger.initialize(log_level="INFO")

    conn = sqlite3.connect(args.db_path, timeout=30)
    conn.row_factory = sqlite3.Row

    query = (
        "SELECT DRPID, source_url, title, summary, data_types "
        "FROM projects ORDER BY DRPID"
    )
    if args.limit > 0:
        query += f" LIMIT {args.limit}"

    updated = 0
    unchanged = 0
    cleared = 0
    skipped = 0
    failed = 0
    browser_session: PlaywrightFetchSession | None = None

    try:
        for row in conn.execute(query):
            drpid = row["DRPID"]
            existing = (row["data_types"] or "").strip()
            if args.only_empty and existing:
                skipped += 1
                continue

            source_url = row["source_url"] or ""
            rds_id = rds_id_from_source_url(source_url)
            if not rds_id:
                skipped += 1
                continue

            meta_url = metadata_url_for_rds_id(rds_id)
            status, html, browser_session = _fetch_metadata_html(
                meta_url,
                browser_session=browser_session,
                use_browser_only=args.browser,
            )
            if status != 200 or not html:
                failed += 1
                print(f"DRPID {drpid}: fetch failed ({status}) {meta_url}", file=sys.stderr)
                time.sleep(args.delay)
                continue

            inferred = infer_data_types(
                row["title"] or "",
                row["summary"] or "",
                html,
            )
            if inferred != existing:
                conn.execute(
                    "UPDATE projects SET data_types = ? WHERE DRPID = ?",
                    (inferred or None, drpid),
                )
                conn.commit()
                updated += 1
                if inferred:
                    print(f"DRPID {drpid}: {inferred}")
                else:
                    cleared += 1
                    print(f"DRPID {drpid}: (cleared)")
            else:
                unchanged += 1

            time.sleep(args.delay)
    finally:
        if browser_session is not None:
            browser_session.__exit__(None, None, None)

    conn.close()
    print(
        f"Done: updated={updated} unchanged={unchanged} cleared={cleared} "
        f"skipped={skipped} failed={failed} db={args.db_path}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
