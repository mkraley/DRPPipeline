"""Analyze Ag Data Commons datasets via the Figshare public API."""
from __future__ import annotations

import statistics
import time
from collections import Counter
from typing import Any
from urllib.parse import urlparse

import requests

HEADERS = {"User-Agent": "DRPPipeline-Research/1.0"}
SEARCH_TERM = "USDA.ADC"
PAGE_SIZE = 100


def search_adc_article_ids(max_pages: int = 20) -> list[int]:
    """Collect Ag Data Commons article IDs from Figshare search."""
    article_ids: list[int] = []
    seen: set[int] = set()
    for page in range(1, max_pages + 1):
        response = requests.post(
            "https://api.figshare.com/v2/articles/search",
            json={"search_for": SEARCH_TERM, "page_size": PAGE_SIZE, "page": page},
            headers=HEADERS,
            timeout=60,
        )
        response.raise_for_status()
        batch: list[dict[str, Any]] = response.json()
        if not batch:
            break
        for item in batch:
            public_url = item.get("url_public_html") or ""
            if "agdatacommons.nal.usda.gov" not in public_url:
                continue
            article_id = int(item["id"])
            if article_id not in seen:
                seen.add(article_id)
                article_ids.append(article_id)
        if len(batch) < PAGE_SIZE:
            break
        time.sleep(0.15)
    return article_ids


def fetch_article(article_id: int) -> dict[str, Any]:
    """Fetch full article metadata from Figshare."""
    response = requests.get(
        f"https://api.figshare.com/v2/articles/{article_id}",
        headers=HEADERS,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def classify_download_host(download_url: str) -> str:
    """Classify where downloadable content is hosted."""
    host = urlparse(download_url).netloc.lower()
    if "ndownloader.figshare.com" in host or "figshare.com" in host:
        return "figshare"
    if "doi.org" in host:
        return "external_doi"
    if host:
        return host
    return "unknown"


def analyze_articles(article_ids: list[int], sample_size: int = 80) -> None:
    """Print summary statistics for a sample of ADC articles."""
    sample = article_ids[:sample_size]
    item_types: Counter[str] = Counter()
    licenses: Counter[str] = Counter()
    download_hosts: Counter[str] = Counter()
    file_counts: list[int] = []
    total_bytes: list[int] = []
    doi_prefixes: Counter[str] = Counter()
    custom_field_presence: Counter[str] = Counter()
    external_only = 0
    missing_files = 0

    for article_id in sample:
        article = fetch_article(article_id)
        item_types[article.get("defined_type_name", "?")] += 1
        license_name = ""
        license_obj = article.get("license")
        if isinstance(license_obj, dict):
            license_name = license_obj.get("name") or "?"
        licenses[license_name] += 1

        doi = article.get("doi") or ""
        if doi:
            doi_prefixes[doi.split("/")[0] + "/" + doi.split("/")[1]] += 1

        files = article.get("files") or []
        file_counts.append(len(files))
        byte_total = sum((file_obj.get("size") or 0) for file_obj in files)
        total_bytes.append(byte_total)
        if not files:
            missing_files += 1
        elif byte_total == 0:
            external_only += 1

        for file_obj in files:
            download_hosts[classify_download_host(file_obj.get("download_url") or "")] += 1

        for field in article.get("custom_fields") or []:
            if field.get("value"):
                custom_field_presence[field.get("name", "?")] += 1

        time.sleep(0.05)

    print(f"Sample size: {len(sample)}")
    print(f"Total enumerated via search: {len(article_ids)}")
    print(f"Item types: {dict(item_types)}")
    print(f"Licenses: {dict(licenses)}")
    print(f"DOI prefixes: {dict(doi_prefixes)}")
    print(
        "Files per item: "
        f"min={min(file_counts)} median={statistics.median(file_counts):.1f} "
        f"max={max(file_counts)}"
    )
    nonzero = [value for value in total_bytes if value > 0]
    if nonzero:
        print(
            "Hosted bytes (non-zero only, MB): "
            f"min={min(nonzero)/1e6:.2f} median={statistics.median(nonzero)/1e6:.2f} "
            f"max={max(nonzero)/1e6:.2f}"
        )
    print(f"Items with no files: {missing_files}")
    print(f"Items with zero-byte files (likely external links): {external_only}")
    print(f"Download host counts: {dict(download_hosts)}")

    common_fields = [
        "Data contact name",
        "Publisher",
        "Temporal Extent Start Date",
        "Geographic Coverage",
        "Public Access Level",
        "Ag Data Commons Group",
    ]
    print("Custom field fill rates:")
    for field_name in common_fields:
        rate = custom_field_presence[field_name] / len(sample) * 100
        print(f"  {field_name}: {rate:.0f}%")


def main() -> None:
    """Run ADC analysis."""
    article_ids = search_adc_article_ids(max_pages=15)
    print(f"Enumerated {len(article_ids)} Ag Data Commons article IDs")
    analyze_articles(article_ids, sample_size=min(80, len(article_ids)))


if __name__ == "__main__":
    main()
