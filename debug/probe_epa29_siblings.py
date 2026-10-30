"""Compare resource URL hosts used by nearby FRS ER projects."""

from __future__ import annotations

import json
import re
import sqlite3
import urllib.request
from pathlib import Path

from collectors.DataGovCatalogClient import DataGovCatalogClient


def main() -> None:
    """Show resource URLs for DRPID 29 and nearby ER_* rows if fetchable."""
    cfg = json.loads(Path("config.json").read_text(encoding="utf-8-sig"))
    epa = cfg["sources"]["epa"]
    client = DataGovCatalogClient(
        gsa_api_key=epa["gsa_api_key"],
        org_slug=epa.get("org_slug", "epa"),
    )
    # Try whatever method the client uses for a package
    methods = [name for name in dir(client) if not name.startswith("_")]
    print("client methods:", methods)

    conn = sqlite3.connect("epa.db")
    rows = conn.execute(
        """
        select DRPID, title, source_url, folder_path, status, errors
        from projects
        where DRPID between 28 and 35
        order by DRPID
        """
    ).fetchall()
    for row in rows:
        print("\n====", row[0], row[1], row[4])
        print("source:", row[2])
        print("folder:", row[3])
        if row[5]:
            print("errors:", (row[5] or "")[:240].replace("\n", " | "))
        folder = Path(row[3]) if row[3] else None
        if folder and folder.exists():
            print("files:", [p.name for p in folder.iterdir()])

    # Inspect how metadata extractor gets resource URLs for one successful ER sibling
    print("\n=== fetch package via catalog client for id 29 source ===")
    source = (
        "https://catalog.data.gov/dataset/"
        "epa-facility-registry-service-frs-er_wwtp_npdes"
    )
    for attr in ("get_package", "fetch_package", "package_show", "get_dataset"):
        if hasattr(client, attr):
            try:
                result = getattr(client, attr)(source)
                print(attr, type(result), str(result)[:500])
            except Exception as exc:  # noqa: BLE001
                print(attr, "failed", exc)

    # Direct HTML resource section extraction with broader pattern
    html = Path("debug/epa29_catalog.html").read_text(encoding="utf-8-sig")
    # data-json or distribution URLs often in script tags
    for label, pattern in [
        ("href resource", r'href="(https?://[^"]+)"'),
        ("json url fields", r'"(?:url|accessURL|downloadURL)"\s*:\s*"(https?://[^"]+)"'),
    ]:
        found = sorted(
            {
                m
                for m in re.findall(pattern, html)
                if any(
                    k in m.lower()
                    for k in ("igeo", "v18", "gispub", "edg", "arcgis", "download", "wafer")
                )
            }
        )
        print(f"\n{label}:")
        for url in found:
            print(" ", url)

    conn.close()


if __name__ == "__main__":
    main()
