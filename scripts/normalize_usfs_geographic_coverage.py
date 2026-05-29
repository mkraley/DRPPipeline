"""
Populate geographic_coverage for USFS projects from FGDC metadata pages.

Fetches each catalog record's metadata HTML, maps to ICPSR thesaurus terms, and
updates the database. Low-confidence or unmatched place keywords are appended to
warnings.

Run from repo root:
    python scripts/normalize_usfs_geographic_coverage.py
    python scripts/normalize_usfs_geographic_coverage.py --db-path usfs.db --limit 20
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
    metadata_url_for_rds_id,
    parse_metadata_page,
    rds_id_from_source_url,
)
from utils.IcpsrGeographicNormalizer import (  # noqa: E402
    log_geographic_normalization,
    normalize_geographic_metadata,
)
from utils.Logger import Logger  # noqa: E402
from utils.url_utils import PlaywrightFetchSession, fetch_page_body  # noqa: E402

DEFAULT_DB_PATH = REPO_ROOT / "usfs.db"


def _ensure_column(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("ALTER TABLE projects ADD COLUMN geographic_coverage TEXT")
        conn.commit()
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e).lower():
            raise


def _append_warning(conn: sqlite3.Connection, drpid: int, message: str) -> None:
    row = conn.execute("SELECT warnings FROM projects WHERE DRPID = ?", (drpid,)).fetchone()
    existing = (row[0] or "").strip() if row else ""
    if message in existing.splitlines():
        return
    new_val = f"{existing}\n{message}".strip() if existing else message
    conn.execute("UPDATE projects SET warnings = ? WHERE DRPID = ?", (new_val, drpid))


def _fetch_metadata_html(
    url: str,
    *,
    browser_session: PlaywrightFetchSession | None,
    use_browser_only: bool,
) -> tuple[int, str, PlaywrightFetchSession | None]:
    """
    Fetch metadata HTML, reusing a Playwright session when HTTP/requests fails.

    On SSL or other HTTP failures, opens one shared browser for the rest of the run.
    """
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
    parser = argparse.ArgumentParser(description="Normalize USFS geographic_coverage in DB")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--limit", type=int, default=0, help="Max records (0 = all)")
    parser.add_argument("--delay", type=float, default=0.15, help="Seconds between HTTP requests")
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Fetch metadata with Playwright only (recommended when requests SSL fails)",
    )
    args = parser.parse_args()

    Logger.initialize(log_level="INFO")

    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row
    _ensure_column(conn)

    query = "SELECT DRPID, source_url, warnings FROM projects ORDER BY DRPID"
    if args.limit > 0:
        query += f" LIMIT {args.limit}"

    updated = 0
    skipped = 0
    failed = 0
    browser_session: PlaywrightFetchSession | None = None

    try:
        for row in conn.execute(query):
            drpid = row["DRPID"]
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

            parsed = parse_metadata_page(html)
            geo = normalize_geographic_metadata(
                geographic_extent_description=parsed.get("geographic_extent_description", ""),
                place_keywords=parsed.get("place_keywords"),
                bounding_box=parsed.get("bounding_box"),
            )
            log_geographic_normalization(
                geo,
                geographic_extent_description=parsed.get("geographic_extent_description", ""),
                place_keywords=parsed.get("place_keywords"),
                bounding_box=parsed.get("bounding_box"),
                context=f"DRPID {drpid} ({rds_id})",
            )

            if geo.geographic_coverage:
                conn.execute(
                    "UPDATE projects SET geographic_coverage = ? WHERE DRPID = ?",
                    (geo.geographic_coverage, drpid),
                )
                updated += 1
            else:
                skipped += 1

            for warning in geo.warnings:
                _append_warning(conn, drpid, warning)

            time.sleep(args.delay)
    finally:
        if browser_session is not None:
            browser_session.__exit__(None, None, None)

    conn.commit()
    conn.close()
    print(
        f"Done: updated={updated} skipped={skipped} failed={failed} db={args.db_path}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
