"""Parse saved catalog HTML and probe FRS_Wastewater mirror."""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path


def main() -> None:
    """Extract resource-like URLs and inspect FRS_Wastewater."""
    html = Path("debug/epa29_catalog.html").read_text(encoding="utf-8-sig")
    urls = set(re.findall(r"https?://[^\s\"'<>]+", html))
    keys = (
        "igeo",
        "gispub",
        "v18",
        "edg",
        "download",
        "arcgis",
        "wafer",
        "frs",
        "hub",
        "resource",
        "zip",
        "geoplatform",
        "maps.arcgis",
    )
    print("=== interesting catalog URLs ===")
    for url in sorted(urls):
        if any(key in url.lower() for key in keys):
            print(url)

    # Also search for resource blocks with truncated-looking hosts in raw html
    for pattern in (
        r"igeo\.epa\.gov[^\"'\\s<>]*",
        r"v18[^\"'\\s<>]*",
        r"WAFer[^\"'\\s<>]*",
        r"gispub\.epa\.gov[^\"'\\s<>]*",
    ):
        print(f"\n=== matches {pattern} ===")
        for match in sorted(set(re.findall(pattern, html, flags=re.I))):
            print(match)

    print("\n=== FRS_Wastewater MapServer ===")
    req = urllib.request.Request(
        "https://gispub.epa.gov/arcgis/rest/services/OEI/FRS_Wastewater/MapServer?f=json",
        headers={"User-Agent": "DRPPipeline/1.0"},
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.load(resp)
    print("mapName:", data.get("mapName"))
    print("description:", (data.get("serviceDescription") or data.get("description") or "")[:500])
    print("layers:")
    for layer in data.get("layers") or []:
        print(" ", layer.get("id"), layer.get("name"))

    # Compare collected sibling ER datasets for URL patterns
    print("\n=== check sibling ER project collected folders if present ===")
    base = Path(r"C:\DataRescue\EPAData")
    if base.exists():
        for folder in sorted(base.glob("EPA00003*"))[:5]:
            print(folder.name, [p.name for p in folder.iterdir()][:8])


if __name__ == "__main__":
    main()
