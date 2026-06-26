"""Tally Publisher custom field for a sample of OAI portal_1059 articles."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sourcing.AdcApiClient import AdcApiClient

SAMPLE_SIZE = 50
OAI_PAGES = (SAMPLE_SIZE + 9) // 10  # 10 IDs per OAI page


def publisher_from_article(article: dict) -> str:
    """Return Publisher custom field value or a fallback label."""
    for field in article.get("custom_fields") or []:
        if not isinstance(field, dict):
            continue
        if str(field.get("name") or "").strip().lower() == "publisher":
            value = str(field.get("value") or "").strip()
            if value:
                return value
    doi = str(article.get("doi") or "").strip()
    if doi.startswith("10.5061/dryad"):
        return "(no Publisher field; Dryad DOI)"
    if doi.startswith("10.5281/zenodo"):
        return "(no Publisher field; Zenodo DOI)"
    if doi.startswith("10.15482/USDA.ADC"):
        return "(no Publisher field; USDA.ADC DOI)"
    return "(no Publisher field)"


def main() -> None:
    """Harvest OAI sample and print publisher tallies."""
    api = AdcApiClient(request_delay=0.05)
    article_ids = api.harvest_portal_article_ids(max_pages=OAI_PAGES)[:SAMPLE_SIZE]
    publishers: Counter[str] = Counter()
    examples: dict[str, list[str]] = {}

    for article_id in article_ids:
        article = api.fetch_article(article_id)
        publisher = publisher_from_article(article)
        publishers[publisher] += 1
        title = str(article.get("title") or "")[:70]
        examples.setdefault(publisher, []).append(f"{article_id}: {title}")

    print(f"OAI portal_1059 sample: {len(article_ids)} articles ({OAI_PAGES} pages)\n")
    print("Publisher tally:")
    for name, count in publishers.most_common():
        print(f"  {count:3d}  {name}")
    print("\nOne example per publisher:")
    for name, _count in publishers.most_common():
        print(f"  [{name}]")
        print(f"    {examples[name][0]}")


if __name__ == "__main__":
    main()
