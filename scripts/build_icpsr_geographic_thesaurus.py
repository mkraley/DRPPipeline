"""
Download ICPSR Geographic Names Thesaurus terms into data/icpsr_geographic_thesaurus.json.

Browses letter-index pages linked from the main thesaurus page, then fetches each
term page for preferred-term aliases when present.

Run from repo root:
    python scripts/build_icpsr_geographic_thesaurus.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from utils.url_utils import fetch_page_body  # noqa: E402

THESAURUS_ID = "10003"
BASE_URL = f"https://www.icpsr.umich.edu/web/ICPSR/thesaurus/{THESAURUS_ID}"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "icpsr_geographic_thesaurus.json"

TERM_LINK_RE = re.compile(rf"/thesaurus/{THESAURUS_ID}/terms/(\d+)")
PREFERRED_RE = re.compile(r"Preferred\s+Term\s*:\s*(.+)", re.IGNORECASE)


def _letter_index_urls(main_html: str) -> list[str]:
    soup = BeautifulSoup(main_html, "html.parser")
    urls: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if f"/thesaurus/{THESAURUS_ID}" not in href or "/terms/" in href:
            continue
        if "letter=" not in href:
            continue
        if href.startswith("/"):
            urls.append("https://www.icpsr.umich.edu" + href)
        elif href.startswith("http"):
            urls.append(href)
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _terms_from_index_html(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    terms: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        m = TERM_LINK_RE.search(a["href"])
        if not m:
            continue
        name = a.get_text(strip=True)
        if name.endswith("*"):
            name = name[:-1].strip()
        if name:
            terms[name] = a["href"]
    return terms


def _aliases_from_term_page(html: str, preferred: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    aliases: list[str] = []
    text = soup.get_text("\n", strip=True)
    for line in text.splitlines():
        m = PREFERRED_RE.search(line)
        if m:
            alias = m.group(1).strip()
            if alias and alias != preferred:
                aliases.append(alias)
    return aliases


def build_thesaurus(*, fetch_aliases: bool = True, delay_sec: float = 0.12) -> dict:
    status, main_html, _, _ = fetch_page_body(BASE_URL)
    if status != 200 or not main_html:
        raise RuntimeError(f"Failed to fetch thesaurus index ({status})")

    term_links = _terms_from_index_html(main_html)
    for index_url in _letter_index_urls(main_html):
        idx_status, idx_html, _, _ = fetch_page_body(index_url)
        if idx_status == 200 and idx_html:
            term_links.update(_terms_from_index_html(idx_html))
        time.sleep(delay_sec)

    entries: list[dict] = []
    for preferred, href in sorted(term_links.items(), key=lambda x: x[0].lower()):
        aliases: list[str] = []
        if fetch_aliases:
            url = href if href.startswith("http") else f"https://www.icpsr.umich.edu{href}"
            t_status, t_html, _, _ = fetch_page_body(url)
            if t_status == 200 and t_html:
                aliases = _aliases_from_term_page(t_html, preferred)
            time.sleep(delay_sec)
        entries.append({"preferred": preferred, "aliases": aliases})

    return {
        "thesaurus_id": THESAURUS_ID,
        "source_url": BASE_URL,
        "term_count": len(entries),
        "terms": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ICPSR geographic thesaurus JSON")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output JSON path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--no-aliases",
        action="store_true",
        help="Skip per-term page fetches (faster; aliases list empty)",
    )
    args = parser.parse_args()

    data = build_thesaurus(fetch_aliases=not args.no_aliases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {data['term_count']} terms to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
