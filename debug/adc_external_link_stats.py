"""Count ADC projects with external link-only file placeholders."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sourcing.AdcApiClient import AdcApiClient
from sourcing.AdcFileInventory import AdcFileInventory


def db_stats(db_path: Path) -> None:
    """Print sourcing-time proxies for external-link records."""
    connection = sqlite3.connect(db_path)
    zero_html = connection.execute(
        "SELECT COUNT(1) FROM projects WHERE file_size = ? AND extensions = ?",
        ("0 B", "html"),
    ).fetchone()[0]
    zero_total = connection.execute(
        "SELECT COUNT(1) FROM projects WHERE file_size = ?",
        ("0 B",),
    ).fetchone()[0]
    sourced_error = connection.execute(
        "SELECT COUNT(1) FROM projects WHERE status = ?",
        ("sourced-error",),
    ).fetchone()[0]
    samples = connection.execute(
        "SELECT DRPID, title FROM projects WHERE file_size = ? AND extensions = ? LIMIT 5",
        ("0 B", "html"),
    ).fetchall()
    connection.close()
    print(f"0 B + html extension (likely link-only): {zero_html}")
    print(f"0 B total: {zero_total}")
    print(f"sourced-error: {sourced_error}")
    print("Samples:")
    for row in samples:
        print(f"  DRPID {row[0]}: {row[1]}")


def api_sample(limit: int = 809) -> None:
    """Classify hosting for catalog IDs (uses Figshare API)."""
    client = AdcApiClient(request_delay=0.05)
    inventory = AdcFileInventory()
    article_ids = client.list_adc_article_ids()
    counts = {
        "figshare": 0,
        "dryad": 0,
        "zenodo": 0,
        "external-unresolved": 0,
        "none": 0,
        "link_only_non_doi": 0,
        "fetch_failed": 0,
    }
    for index, article_id in enumerate(article_ids[:limit], 1):
        try:
            article = client.fetch_article(article_id)
        except Exception:
            counts["fetch_failed"] += 1
            continue
        hosting = inventory.classify_hosting(article)
        counts[hosting] = counts.get(hosting, 0) + 1
        files = article.get("files") or []
        if len(files) == 1 and int(files[0].get("size") or 0) == 0:
            download_url = str(files[0].get("download_url") or "")
            if "doi.org" not in download_url and files[0].get("is_link_only"):
                counts["link_only_non_doi"] += 1
        if index % 100 == 0:
            print(f"  API progress: {index}/{len(article_ids)}")
    print("API hosting classification:")
    for key, value in counts.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "adc.db"
    print("=== Database proxies ===")
    db_stats(db_path)
    if "--api" in sys.argv:
        print()
        print("=== Figshare API scan ===")
        api_sample()
