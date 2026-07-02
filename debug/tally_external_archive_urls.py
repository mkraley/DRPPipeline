"""Tally external-archive URLs from adc.db status_notes (read-only analysis)."""

from __future__ import annotations

import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

URL_IN_NOTES = re.compile(r"https?://[^\s\]\)\"\'<>]+", re.IGNORECASE)
STATUS = "collected - external archive"


def extract_urls(status_notes: str | None) -> list[str]:
    """Parse external URLs from status_notes text."""
    if not status_notes:
        return []
    text = status_notes.strip()
    urls: list[str] = []
    if text.startswith("External data URL:"):
        urls.append(text.split(":", 1)[1].strip())
    elif text.startswith("External data URLs:"):
        for line in text.splitlines()[1:]:
            line = line.strip()
            if line.startswith("http"):
                urls.append(line)
    else:
        urls.extend(URL_IN_NOTES.findall(text))
    return urls


def normalize_domain(url: str) -> str:
    """Return host with leading www. removed."""
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or "(invalid)"


def registrable_domain(host: str) -> str:
    """Approximate registrable domain for grouping (simple heuristic)."""
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    # gov/edu second-level domains
    if len(parts) >= 3 and parts[-2] in ("gov", "edu", "co", "ac"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def feasibility_hint(domain: str, count: int) -> str:
    """Short automation feasibility note for a domain grouping."""
    hints: dict[str, str] = {
        "ars.usda.gov": "USDA ARS web apps; often HTML landing pages, not direct files. Playwright + link discovery may work per site; no shared API.",
        "usda.gov": "USDA program pages; mixed static downloads and portals. Site-specific scraping; some /download/ paths are direct files.",
        "nal.usda.gov": "NAL discovery/catalog UI; metadata portal, not bulk file API. Hard to automate without interactive flow.",
        "lcacommons.gov": "LCA Commons portal; domain-specific UI. Would need dedicated collector or interactive_collector.",
        "rosaceae.org": "GDR database; registration/download UI. Interactive or custom API if available.",
        "agmip.org": "AgMIP tools portal; web tools not file dumps. Likely interactive_collector only.",
        "sc.egov.usda.gov": "Geospatial Data Gateway; account/download workflow. Not trivial to batch automate.",
        "ars-grin.gov": "GRIN/NPGS databases; search UI for specimens. Interactive cataloging, not file harvest.",
        "si.edu": "Smithsonian collections search; web UI. Interactive_collector territory.",
        "medius.re": "Third-party project site (NE potato DB); unknown structure; case-by-case.",
        "northcentralwater.org": "Project landing page; likely manual/interactive.",
        "errc.ars.usda.gov": "ARS center portal; HTML landing page.",
        "nrrl.ncaur.usda.gov": "Culture collection catalog; database UI not file export.",
        "app.globus.org": "Globus File Manager endpoints (origin_id UUID). Globus Transfer API + auth feasible for batch harvest; same pattern across 35 records — highest ROI for automation.",
        "globus.org": "Globus platform; see app.globus.org.",
        "zenodo.org": "Zenodo API exists; high automation feasibility for record/file download.",
        "datadryad.org": "Dryad API exists; high automation feasibility.",
    }
    for key, hint in hints.items():
        if domain == key or domain.endswith("." + key):
            return hint
    if count >= 5:
        return f"{count} records on same domain — worth a dedicated collector module if structure is consistent."
    return "Low volume or one-off; interactive_collector or manual likely sufficient."


def main(db_path: Path) -> None:
    """Print domain tally and automation notes."""
    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        """
        SELECT DRPID, title, status_notes, source_url
        FROM projects
        WHERE status = ?
        ORDER BY DRPID
        """,
        (STATUS,),
    ).fetchall()
    connection.close()

    by_domain: Counter[str] = Counter()
    by_reg_domain: Counter[str] = Counter()
    no_url: list[tuple[int, str]] = []
    domain_to_drpids: defaultdict[str, list[int]] = defaultdict(list)
    domain_to_urls: defaultdict[str, set[str]] = defaultdict(set)

    for drpid, title, status_notes, _source_url in rows:
        urls = extract_urls(status_notes)
        if not urls:
            no_url.append((drpid, title or ""))
            continue
        for url in urls:
            domain = normalize_domain(url)
            by_domain[domain] += 1
            by_reg_domain[registrable_domain(domain)] += 1
            domain_to_drpids[domain].append(drpid)
            domain_to_urls[domain].add(url)

    print(f"Database: {db_path}")
    print(f"External archive records: {len(rows)}")
    print(f"With URL in status_notes: {len(rows) - len(no_url)}")
    print(f"Missing URL in status_notes: {len(no_url)}")
    print()

    print("=== By hostname (sorted by count) ===")
    for domain, count in by_domain.most_common():
        sample = next(iter(domain_to_urls[domain]))
        drp_sample = domain_to_drpids[domain][:5]
        print(f"  {count:3d}  {domain}")
        print(f"       sample: {sample[:90]}")
        print(f"       DRPIDs: {drp_sample}{'...' if len(domain_to_drpids[domain]) > 5 else ''}")
        print(f"       note: {feasibility_hint(domain, count)}")
        print()

    print("=== By registrable domain (grouped) ===")
    for reg, count in by_reg_domain.most_common():
        print(f"  {count:3d}  {reg}")

    if no_url:
        print()
        print("=== No URL in status_notes (pre-feature or empty file list) ===")
        for drpid, title in no_url[:15]:
            print(f"  DRPID {drpid}: {(title or '')[:60]}")
        if len(no_url) > 15:
            print(f"  ... and {len(no_url) - 15} more")

    globus_rows = [
        extract_urls(r[2])[0]
        for r in rows
        if r[2] and "globus" in r[2].lower()
    ]
    if globus_rows:
        import re

        origin_ids: set[str] = set()
        origin_paths: set[str] = set()
        for url in globus_rows:
            match = re.search(r"origin_id=([0-9a-f-]+)", url, re.I)
            if match:
                origin_ids.add(match.group(1))
            path_match = re.search(r"origin_path=([^&\\s]+)", url, re.I)
            if path_match:
                origin_paths.add(path_match.group(1))
        print()
        print("=== Globus subset ===")
        print(f"  Records: {len(globus_rows)}")
        print(f"  Unique origin_id values: {len(origin_ids)}")
        print(f"  Unique origin_path values: {len(origin_paths)}")
        print(f"  Pattern: app.globus.org/file-manager?origin_id=<UUID>&origin_path=...")


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "adc.db"
    main(path)
