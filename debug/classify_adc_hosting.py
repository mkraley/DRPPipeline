"""Classify ADC dataset hosting for inventory estimates (debug helper)."""

from __future__ import annotations

import time
from collections import Counter

from sourcing.AdcApiClient import AdcApiClient
from sourcing.AdcFileInventory import AdcFileInventory


def main() -> None:
    """Print hosting-type counts for merged ADC article IDs."""
    api = AdcApiClient(request_delay=0.05)
    inventory = AdcFileInventory()
    article_ids = api.merge_article_ids()
    hosting = Counter()
    doi_prefix = Counter()
    only_search = set(api.list_adc_article_ids())
    only_oai = set(api.harvest_portal_article_ids()) - only_search

    for index, article_id in enumerate(article_ids, 1):
        article = api.fetch_article(article_id)
        hosting[inventory.classify_hosting(article)] += 1
        doi = str(article.get("doi") or "")
        if doi:
            parts = doi.split("/", 2)
            prefix = "/".join(parts[:2]) if len(parts) >= 2 else doi
            doi_prefix[prefix] += 1
        if index % 50 == 0:
            print(f"... classified {index}/{len(article_ids)}")
        time.sleep(0.05)

    print(f"Total merged article IDs: {len(article_ids)}")
    print(f"  USDA.ADC search only: {len(only_search - only_oai)}")
    print(f"  OAI portal_1059 only (not in search): {len(only_oai)}")
    print(f"  Overlap: {len(only_search & set(article_ids)) - len(only_oai)}")
    print("Hosting classification:")
    for label, count in hosting.most_common():
        print(f"  {label}: {count}")
    print("Top DOI prefixes:")
    for label, count in doi_prefix.most_common(8):
        print(f"  {label}: {count}")


if __name__ == "__main__":
    main()
