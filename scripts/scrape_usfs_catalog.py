"""
Index USFS Research Data Archive catalog entries into usfs.db (``projects`` schema).

Fetches listing pages from https://www.fs.usda.gov/rds/archive/catalog and writes
each page to the database immediately (so a later page failure does not discard
earlier inserts).

Run from repo root:
    python scripts/scrape_usfs_catalog.py
    python scripts/scrape_usfs_catalog.py --limit 50

Existing rows (same source_url) are left unchanged.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from sourcing.UsfsCatalogCandidateFetcher import (  # noqa: E402
    DEFAULT_PAGE_SIZE,
    fetch_catalog_page,
)
from storage import Storage  # noqa: E402
from utils.Logger import Logger  # noqa: E402

DEFAULT_DB_PATH = REPO_ROOT / "usfs.db"


def populate_db(rows: list[dict[str, str]]) -> tuple[int, int]:
    """
    Insert each row into ``projects`` if source_url is new.

    Returns:
        (inserted_count, skipped_existing_count)
    """
    inserted = 0
    skipped = 0
    for row in rows:
        source_url = row["url"]
        if Storage.exists_by_source_url(source_url):
            skipped += 1
            continue
        drpid = Storage.create_record(source_url)
        Storage.update_record(
            drpid,
            {
                "title": row.get("title", ""),
                "agency": row.get("agency", ""),
                "office": row.get("office", ""),
                "status": "sourced",
            },
        )
        inserted += 1
    return inserted, skipped


def index_catalog(
    *,
    limit: int | None,
    timeout: int,
    max_retries: int,
    page_delay: float,
) -> tuple[int, int, int, int]:
    """
    Walk the catalog, inserting each page as it is fetched.

    Returns:
        (pages_processed, entries_seen, inserted_total, skipped_total)
    """
    page_index = 1
    entries_seen = 0
    inserted_total = 0
    skipped_total = 0
    pages_processed = 0

    while True:
        if limit is not None and entries_seen >= limit:
            break

        page_rows, status = fetch_catalog_page(
            page_index,
            timeout=timeout,
            max_retries=max_retries,
        )
        if status != 200:
            print(
                f"Stopped at catalog page {page_index}: fetch failed (status={status}). "
                f"Earlier pages are already saved in the database.",
                file=sys.stderr,
            )
            break

        if not page_rows:
            print(f"Catalog page {page_index}: no entries (end of catalog).", file=sys.stderr)
            break

        if limit is not None:
            remaining = limit - entries_seen
            page_rows = page_rows[:remaining]

        inserted, skipped = populate_db(page_rows)
        inserted_total += inserted
        skipped_total += skipped
        entries_seen += len(page_rows)
        pages_processed += 1

        print(
            f"Catalog page {page_index}: {len(page_rows)} entries, "
            f"inserted {inserted}, skipped {skipped} (running totals: "
            f"{inserted_total} inserted, {skipped_total} skipped)",
            file=sys.stderr,
        )

        if len(page_rows) < DEFAULT_PAGE_SIZE:
            break
        if limit is not None and entries_seen >= limit:
            break

        page_index += 1
        if page_delay > 0:
            time.sleep(page_delay)

    return pages_processed, entries_seen, inserted_total, skipped_total


def main() -> None:
    parser = argparse.ArgumentParser(description="Index USFS RDS catalog into usfs.db")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max catalog entries to process (default: all)",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite database path (default: {DEFAULT_DB_PATH.name})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="HTTP timeout per catalog page in seconds (default: 60)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Retries per catalog page on fetch failure (default: 3)",
    )
    parser.add_argument(
        "--page-delay",
        type=float,
        default=0.5,
        help="Seconds to wait between catalog pages (default: 0.5)",
    )
    args = parser.parse_args()

    Logger.initialize(log_level="WARNING")
    Storage.reset()
    Storage.initialize("StorageSQLLite", db_path=args.db_path)

    print(f"Indexing USFS catalog into {args.db_path} ...", file=sys.stderr)

    pages, seen, inserted, skipped = index_catalog(
        limit=args.limit,
        timeout=args.timeout,
        max_retries=args.max_retries,
        page_delay=args.page_delay,
    )

    print(
        f"Done: {pages} catalog page(s), {seen} entries seen, "
        f"{inserted} inserted, {skipped} skipped (already in DB).",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
