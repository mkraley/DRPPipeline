"""Probe the GWDA nomination lookup form for existing vs missing URLs."""

from __future__ import annotations

import re

import requests

HOME = "https://digital2.library.unt.edu/nomination/GWDA-US-2025/"
LOOKUP = "https://digital2.library.unt.edu/nomination/GWDA-US-2025/lookup/"
URLS = [
    "https://example.com/not-a-real-gwda-url-xyz",
    "https://www.nps.gov/",
    "https://irma.nps.gov/DataStore/",
]


def main() -> None:
    """POST sample URLs and print how the lookup page responds."""
    session = requests.Session()
    home = session.get(HOME, timeout=30)
    match = re.search(
        r'name="csrfmiddlewaretoken" value="([^"]+)"',
        home.text,
    )
    token = match.group(1) if match else ""
    print(f"home {home.status_code} token_len {len(token)}")
    for url in URLS:
        response = session.post(
            LOOKUP,
            data={"csrfmiddlewaretoken": token, "search-url-value": url},
            headers={"Referer": HOME},
            timeout=30,
            allow_redirects=True,
        )
        title_match = re.search(r"<title>([^<]+)</title>", response.text)
        title = title_match.group(1).strip() if title_match else ""
        print("---")
        print(url)
        print(f"status {response.status_code} final {response.url}")
        print(f"title {title} len {len(response.text)}")
        lowered = response.text.lower()
        for needle in (
            "already",
            "not found",
            "add/edit",
            "nomination score",
            "no results",
            "in scope",
            "capture the following",
            "search by url",
        ):
            if needle in lowered:
                print(f"  has {needle}")


if __name__ == "__main__":
    main()
