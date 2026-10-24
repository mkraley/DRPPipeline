"""Locate the EQR data dictionary that matches the current CSV filings."""

from __future__ import annotations

from bs4 import BeautifulSoup

DICTIONARY_NAME = "dictionary.pdf"
DICTIONARY_LABEL = "Data Dictionary V3.5"
DICTIONARY_FALLBACK_URL = (
    "https://www.ferc.gov/sites/default/files/2020-11/Data_Dictionary_V3_5_Clean.pdf"
)


def dictionary_url_from_html(html: str) -> str:
    """
    Return the V3.5 dictionary URL from the EQR explanation page.

    Version 4.0 belongs to the later XBRL-CSV filing system. The quarterly
    CSV zips still follow V3.5.

    Args:
        html: Explanation-page HTML.

    Returns:
        Absolute URL of the dictionary PDF.
    """
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a"):
        text = " ".join(anchor.get_text(" ", strip=True).split())
        if text != DICTIONARY_LABEL:
            continue
        href = str(anchor.get("href") or "").strip()
        if href.startswith("http"):
            return href
        if href.startswith("/"):
            return f"https://www.ferc.gov{href}"
    return DICTIONARY_FALLBACK_URL
