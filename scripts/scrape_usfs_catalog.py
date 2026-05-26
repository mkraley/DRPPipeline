"""
Index USFS Research Data Archive catalog entries into usfs.db (``projects`` schema).

Fetches listing pages from https://www.fs.usda.gov/rds/archive/catalog to
populate source_url, title, and agency.

Run from repo root:
    python scripts/scrape_usfs_catalog.py
    python scripts/scrape_usfs_catalog.py --limit 5

Existing rows (same source_url) are left unchanged.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from sourcing.UsfsCatalogCandidateFetcher import UsfsCatalogCandidateFetcher  # noqa: E402
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
    args = parser.parse_args()

    Logger.initialize(log_level="WARNING")
    Storage.reset()
    Storage.initialize("StorageSQLLite", db_path=args.db_path)

    fetcher = UsfsCatalogCandidateFetcher()
    rows, _skipped_filter = fetcher.get_candidate_urls(limit=args.limit)
    inserted, skipped = populate_db(rows)

    print(
        f"Processed {len(rows)} catalog entries into {args.db_path}: "
        f"inserted {inserted}, skipped (already present) {skipped}.",
        file=sys.stderr,
    )
    for row in rows:
        print(
            f"  {row['url']}\n"
            f"    title:  {row.get('title', '')}\n"
            f"    agency: {row.get('agency', '')}\n"
            f"    office: {row.get('office', '')}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
