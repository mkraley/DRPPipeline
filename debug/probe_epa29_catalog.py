"""Resolve EPA 29 catalog resources and search alternate ArcGIS hosts."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

API_KEY = "DLjaEG3SuXWWrlgDAO40jZbi4fzRDHiihwoIa5df"
HEADERS = {"User-Agent": "DRPPipeline/1.0", "X-Api-Key": API_KEY}
HTML_HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_json(url: str) -> dict:
    """GET JSON with API key."""
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def get_text(url: str) -> str:
    """GET text body."""
    req = urllib.request.Request(url, headers=HTML_HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def probe(url: str) -> str:
    """Return short status for a URL."""
    req = urllib.request.Request(url, headers=HTML_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read(180).decode("utf-8", errors="replace").replace("\n", " ")
            return f"{resp.status} {body}"
    except urllib.error.HTTPError as exc:
        body = exc.read(120).decode("utf-8", errors="replace").replace("\n", " ")
        return f"HTTP {exc.code} {body}"
    except Exception as exc:  # noqa: BLE001
        return f"ERR {exc}"


def main() -> None:
    """Print catalog resources and probe likely mirrors."""
    for package_id in (
        "33ff5222-d3c6-4e5b-b40a-66b7da3e71eb",
        "epa-facility-registry-service-frs-er_wwtp_npdes",
    ):
        url = f"https://catalog.data.gov/api/3/action/package_show?id={package_id}"
        print(f"=== package_show {package_id} ===")
        try:
            data = get_json(url)
            result = data["result"]
            print("title:", result.get("title"))
            print("name:", result.get("name"))
            for res in result.get("resources") or []:
                print("-", res.get("format"), "|", res.get("name"), "|", res.get("url"))
        except Exception as exc:  # noqa: BLE001
            print("failed:", exc)

    page = (
        "https://catalog.data.gov/dataset/"
        "epa-facility-registry-service-frs-er_wwtp_npdes"
    )
    print("\n=== scrape catalog HTML links ===")
    html = get_text(page)
    Path("debug/epa29_catalog.html").write_text(html, encoding="utf-8-sig")
    urls = sorted(set(re.findall(r"https?://[^\"'\\s<>]+", html)))
    keys = (
        "arcgis",
        "igeo",
        "gispub",
        "edg",
        "download",
        "zip",
        "hub",
        "geoplatform",
        "epa.gov",
        "resource",
    )
    for url in urls:
        if any(key in url.lower() for key in keys):
            print(url)

    # List OEI services and find WWTP / ESF / ER names
    print("\n=== OEI services matching WWTP/ESF/ER ===")
    try:
        oei = get_json("https://gispub.epa.gov/arcgis/rest/services/OEI?f=json")
        for svc in oei.get("services") or []:
            name = svc.get("name") or ""
            if re.search(r"WWTP|ESF|ER_|NPDES|FRS", name, re.I):
                print(svc.get("type"), name)
    except Exception as exc:  # noqa: BLE001
        print("OEI list failed:", exc)

    probes = [
        "https://gispub.epa.gov/arcgis/rest/services/OEI/FRS_ESF3/MapServer?f=json",
        "https://gispub.epa.gov/arcgis/rest/services/OEI/FRS_ER_WWTP_NPDES/MapServer?f=json",
        "https://gispub.epa.gov/arcgis/rest/services/OEI/FRS_WWTP/MapServer?f=json",
        "https://gispub.epa.gov/arcgis/rest/services/OEI/FRS_NPDES/MapServer?f=json",
        "https://edg.epa.gov/metadata/catalog/search/resource/details.page"
        "?uuid=33ff5222-d3c6-4e5b-b40a-66b7da3e71eb",
        "https://edg.epa.gov/metadata/rest/document"
        "?id=33ff5222-d3c6-4e5b-b40a-66b7da3e71eb",
    ]
    print("\n=== probes ===")
    for url in probes:
        print(url)
        print(" ", probe(url))


if __name__ == "__main__":
    main()
