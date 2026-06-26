"""Sample a few ADC articles and classify file hosting patterns."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sourcing.AdcApiClient import AdcApiClient, article_id_from_source_url
from sourcing.AdcFileInventory import AdcFileInventory


def sample_articles(db_path: Path, *, zero_b_limit: int = 5, random_limit: int = 10) -> list[str]:
    """Build a small URL sample: DRP 15, zero-byte rows, and random sourced rows."""
    connection = sqlite3.connect(db_path)
    drp15 = connection.execute(
        "SELECT source_url FROM projects WHERE DRPID = 15",
    ).fetchone()
    zero_rows = connection.execute(
        "SELECT source_url FROM projects WHERE file_size = ? LIMIT ?",
        ("0 B", zero_b_limit),
    ).fetchall()
    random_rows = connection.execute(
        """
        SELECT source_url FROM projects
        WHERE file_size != ? AND status = 'sourced'
        ORDER BY RANDOM() LIMIT ?
        """,
        ("0 B", random_limit),
    ).fetchall()
    connection.close()

    urls: list[str] = []
    seen: set[str] = set()
    if drp15:
        urls.append(str(drp15[0]))
        seen.add(str(drp15[0]))
    for row in zero_rows + random_rows:
        url = str(row[0])
        if url not in seen:
            urls.append(url)
            seen.add(url)
    return urls


def describe_file_pattern(files: list[dict]) -> str:
    """Short human-readable summary of raw Figshare file list."""
    if not files:
        return "no files"
    if len(files) > 1:
        hosted = sum(1 for item in files if int(item.get("size") or 0) > 0)
        return f"{len(files)} figshare entries ({hosted} with size > 0)"
    only = files[0]
    size = int(only.get("size") or 0)
    download_url = str(only.get("download_url") or "")
    if size > 0:
        return f"figshare-hosted ({size} B)"
    if "doi.org" in download_url:
        return f"doi placeholder -> {download_url[:80]}"
    if only.get("is_link_only"):
        return f"link-only -> {download_url[:80]}"
    return f"zero-byte file -> {download_url[:80]}"


def main(db_path: Path) -> None:
    """Print hosting classification for a small sample."""
    client = AdcApiClient(request_delay=0)
    inventory = AdcFileInventory()
    urls = sample_articles(db_path)
    print(f"Sampling {len(urls)} articles from {db_path.name}\n")

    counts: dict[str, int] = {}
    for url in urls:
        article_id = article_id_from_source_url(url)
        if article_id is None:
            continue
        article = client.fetch_article(article_id)
        raw_files = article.get("files") or []
        resolved = inventory.list_files_for_article(article)
        hosting = inventory.classify_hosting(article)
        counts[hosting] = counts.get(hosting, 0) + 1
        title = str(article.get("title") or "")[:60]
        print(f"Article {article_id}: {title}")
        print(f"  pattern: {describe_file_pattern(raw_files)}")
        print(f"  hosting: {hosting}; resolved files: {len(resolved)}")
        for file_row in resolved[:3]:
            source = file_row.get("source")
            name = file_row.get("name")
            size_bytes = file_row.get("size_bytes")
            print(f"    - {source}: {name} ({size_bytes} B)")
        if len(resolved) > 3:
            print(f"    ... and {len(resolved) - 3} more")
        print()

    print("Sample counts by hosting:")
    for key, value in sorted(counts.items()):
        print(f"  {key}: {value}")


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "adc.db"
    main(path)
