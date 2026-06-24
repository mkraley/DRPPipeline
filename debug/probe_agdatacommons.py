"""Temporary probe script for Ag Data Commons API investigation."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

import requests

OAI_NS = {"oai": "http://www.openarchives.org/OAI/2.0/"}
HEADERS = {"User-Agent": "DRPPipeline-Research/1.0"}


def list_oai_sets() -> list[tuple[str, str]]:
    """Return Figshare OAI-PMH set specs and names."""
    response = requests.get(
        "https://api.figshare.com/v2/oai",
        params={"verb": "ListSets"},
        headers=HEADERS,
        timeout=60,
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)
    sets: list[tuple[str, str]] = []
    for node in root.findall(".//oai:set", OAI_NS):
        spec = node.find("oai:setSpec", OAI_NS)
        name = node.find("oai:setName", OAI_NS)
        if spec is not None and spec.text:
            sets.append((spec.text, name.text if name is not None else ""))
    return sets


def search_articles(term: str, page_size: int = 3) -> list[dict[str, Any]]:
    """Search Figshare public articles."""
    response = requests.post(
        "https://api.figshare.com/v2/articles/search",
        json={"search_for": term, "page_size": page_size},
        headers=HEADERS,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def oai_list_identifiers(set_spec: str, limit_hint: int = 1) -> tuple[int | None, list[str]]:
    """List OAI identifiers for a set; return resumption token presence as count hint."""
    response = requests.get(
        "https://api.figshare.com/v2/oai",
        params={
            "verb": "ListIdentifiers",
            "metadataPrefix": "oai_dc",
            "set": set_spec,
        },
        headers=HEADERS,
        timeout=60,
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)
    ids = [
        node.text
        for node in root.findall(".//oai:identifier", OAI_NS)
        if node.text and node.text.startswith("oai:")
    ]
    token = root.find(".//oai:resumptionToken", OAI_NS)
    complete = root.find(".//oai:ListIdentifiers", OAI_NS)
    total = None
    if token is not None and token.get("completeListSize"):
        total = int(token.get("completeListSize", "0"))
    return total, ids[:limit_hint]


def fetch_article(article_id: int) -> dict[str, Any]:
    """Fetch full article metadata from Figshare API."""
    response = requests.get(
        f"https://api.figshare.com/v2/articles/{article_id}",
        headers=HEADERS,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    """Run Ag Data Commons API probes."""
    print("=== Figshare OAI sets matching ag/usda/adc ===")
    sets = list_oai_sets()
    print(f"Total OAI sets: {len(sets)}")
    matches = [
        item
        for item in sets
        if re.search(r"ag|usda|adc|agric|nal", item[1] or "", re.I)
        or re.search(r"ag|usda|adc|nal", item[0] or "", re.I)
    ]
    for spec, name in matches:
        print(f"  {spec}: {name}")

    print("\n=== Figshare article searches ===")
    for term in [
        ":institution: agdatacommons",
        ":institution: nal",
        "Ag Data Commons",
        ":item_type: dataset",
    ]:
        try:
            results = search_articles(term, page_size=2)
            print(f'\nSearch "{term}": {len(results)} on first page')
            for item in results:
                print(
                    f"  id={item.get('id')} type={item.get('defined_type_name')} "
                    f"url={item.get('url_public_html', '')[:80]}"
                )
        except requests.HTTPError as exc:
            print(f'\nSearch "{term}" failed: {exc}')

    print("\n=== Probe likely portal sets ===")
    portal_candidates = [s for s, _ in matches if s.startswith("portal_")]
    for spec in portal_candidates[:5]:
        try:
            total, sample = oai_list_identifiers(spec)
            print(f"  {spec}: completeListSize={total}, sample={sample}")
        except requests.HTTPError as exc:
            print(f"  {spec}: failed {exc}")

    print("\n=== Sample ADC article from portal HTML pattern ===")
    # Known public ADC dataset from web search / common examples
    sample_ids = [30000000, 25000000, 20000000]
    for article_id in sample_ids:
        try:
            article = fetch_article(article_id)
            html = article.get("url_public_html", "")
            if "agdatacommons" in html:
                print(f"Found ADC article {article_id}: {article.get('title', '')[:60]}")
                files = article.get("files", [])
                print(f"  files={len(files)}")
                if files:
                    f0 = files[0]
                    print(
                        f"  first file: name={f0.get('name')} "
                        f"size={f0.get('size')} url={f0.get('download_url', '')[:80]}"
                    )
                break
        except requests.HTTPError:
            continue


if __name__ == "__main__":
    main()
