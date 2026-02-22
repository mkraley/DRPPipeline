"""Check accessgudid page structure - iframes and zip links."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.url_utils import fetch_page_body

def main():
    status, body, ct, _ = fetch_page_body(
        "https://accessgudid.nlm.nih.gov/download", timeout=30
    )
    print("status:", status, "len:", len(body))
    iframes = re.findall(r"<iframe[^>]*>", body, re.I)
    print("iframes:", len(iframes))
    for i in iframes[:3]:
        print(" ", i[:120])
    zip_links = re.findall(r'href=["\']([^"\']*\.zip[^"\']*)["\']', body, re.I)
    print("zip links in raw HTML:", len(zip_links))
    if zip_links:
        print("  first:", zip_links[0][:80])
    # Check one zip link's full tag
    m = re.search(r"<a[^>]*href=[\"']([^\"']*\.zip[^\"']*)[\"'][^>]*>", body, re.I)
    if m:
        start = max(0, m.start() - 20)
        end = min(len(body), m.end() + 50)
        print("Sample zip link tag:", repr(body[start:end]))
    print("--- first 2000 chars ---")
    print(body[:2000])

if __name__ == "__main__":
    main()
