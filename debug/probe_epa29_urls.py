"""Probe EPA DRPID 29 catalog resources and alternate ArcGIS hosts."""

from __future__ import annotations

import json
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_KEY = "DLjaEG3SuXWWrlgDAO40jZbi4fzRDHiihwoIa5df"
DATASET_URL = (
    "https://catalog.data.gov/dataset/epa-facility-registry-service-frs-er_wwtp_npdes"
)
PACKAGE_ID = "epa-facility-registry-service-frs-er_wwtp_npdes"


def fetch(url: str, timeout: int = 45) -> tuple[int | None, str]:
    """Return status code and a short body/error snippet."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "DRPPipeline/1.0", "Accept": "*/*"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(500)
            return resp.status, body[:200].decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read(200).decode("utf-8", errors="replace")
        return exc.code, body
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def package_show(package_id: str) -> dict:
    """Fetch CKAN package_show with GSA API key."""
    qs = urllib.parse.urlencode({"id": package_id})
    url = f"https://api.data.gov/media/data.json?{qs}"
    # Prefer catalog CKAN API with X-Api-Key style used elsewhere.
    url = f"https://catalog.data.gov/api/3/action/package_show?{qs}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "DRPPipeline/1.0",
            "X-Api-Key": API_KEY,
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def main() -> None:
    """Print resources and probe known/alternate endpoints."""
    print("=== catalog package_show ===")
    try:
        data = package_show(PACKAGE_ID)
        result = data.get("result") or {}
        print("title:", result.get("title"))
        print("id:", result.get("id"))
        print("name:", result.get("name"))
        for res in result.get("resources") or []:
            print(
                "-",
                res.get("format"),
                "|",
                (res.get("name") or "")[:70],
                "|",
                res.get("url"),
            )
        urls = [r.get("url") for r in (result.get("resources") or []) if r.get("url")]
    except Exception as exc:  # noqa: BLE001
        print("package_show failed:", exc)
        urls = []

    # Also try CKAN search
    print("\n=== package_search FRS ER_WWTP ===")
    try:
        qs = urllib.parse.urlencode(
            {"q": "FRS ER_WWTP_NPDES", "rows": 10, "fq": "organization:epa-gov"}
        )
        url = f"https://catalog.data.gov/api/3/action/package_search?{qs}"
        req = urllib.request.Request(
            url, headers={"User-Agent": "DRPPipeline/1.0", "X-Api-Key": API_KEY}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        for pkg in data.get("result", {}).get("results", []):
            print("PKG", pkg.get("name"), "|", pkg.get("title"))
            for res in pkg.get("resources") or []:
                print("  ", res.get("format"), res.get("url"))
    except Exception as exc:  # noqa: BLE001
        print("search failed:", exc)

    candidates = [
        "https://igeo.epa.gov/arcgis/rest/services/OEI/FRS_ESF3/MapServer?f=json",
        "https://gispub.epa.gov/arcgis/rest/services/OEI/FRS_ESF3/MapServer?f=json",
        "https://geodata.epa.gov/arcgis/rest/services/OEI/FRS_ESF3/MapServer?f=json",
        "https://gispub.epa.gov/arcgis/rest/services/OEI/FRS_INTERESTS/MapServer?f=json",
        "https://gispub.epa.gov/arcgis/rest/services?f=json",
        "https://igeo.epa.gov/arcgis/rest/services?f=json",
        "https://gispub.epa.gov/arcgis/rest/services/OEI?f=json",
        "https://igeo.epa.gov/",
        "https://edg.epa.gov/",
        DATASET_URL,
    ]
    # Add any resource URLs from catalog
    for u in urls:
        if u not in candidates:
            candidates.append(u)
            if "MapServer" in u or "FeatureServer" in u:
                sep = "&" if "?" in u else "?"
                candidates.append(f"{u}{sep}f=json")

    print("\n=== URL probes ===")
    for url in candidates:
        code, snippet = fetch(url)
        print(f"[{code}] {url}")
        print("   ", snippet.replace("\n", " ")[:160])

    # Look for similar FRS URLs already in epa.db
    print("\n=== similar urls in epa.db ===")
    conn = sqlite3.connect(Path(__file__).resolve().parents[1] / "epa.db")
    rows = conn.execute(
        """
        select DRPID, title, source_url, errors
        from projects
        where title like '%FRS%' or source_url like '%frs%'
        order by DRPID
        limit 40
        """
    ).fetchall()
    for row in rows:
        print(row[0], row[1][:60] if row[1] else None, row[2])
    conn.close()


if __name__ == "__main__":
    main()
