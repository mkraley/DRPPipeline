"""Inspect EPA DRPID 81 resources and probe accessibility."""

from __future__ import annotations

import json
import re
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path


def main() -> None:
    """Print project 81 details and probe its catalog resource URLs."""
    conn = sqlite3.connect("epa.db")
    cols = [r[1] for r in conn.execute("pragma table_info(projects)")]
    row = conn.execute("select * from projects where DRPID=81").fetchone()
    if not row:
        print("DRPID 81 not found")
        return
    data = dict(zip(cols, row, strict=True))
    for key in (
        "DRPID",
        "title",
        "status",
        "source_url",
        "folder_path",
        "errors",
        "status_notes",
        "warnings",
        "collection_notes",
    ):
        print(f"{key}: {data.get(key)}")
    conn.close()

    source = str(data.get("source_url") or "")
    print("\n=== catalog HTML resources ===")
    req = urllib.request.Request(source, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    Path("debug/epa81_catalog.html").write_text(html, encoding="utf-8-sig")
    urls = sorted(set(re.findall(r"https?://[^\s\"'<>]+", html)))
    interesting = [
        u
        for u in urls
        if any(
            k in u.lower()
            for k in (
                "query",
                "csv",
                "xml",
                "json",
                "export",
                "download",
                "resource",
                "socrata",
                "data.epa",
                "arcgis",
                "hub",
            )
        )
    ]
    for url in interesting:
        print(url)

    print("\n=== probes ===")
    for url in interesting:
        probe(url)


def probe(url: str) -> None:
    """HEAD then short GET for one URL."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
    }
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                cl = resp.headers.get("Content-Length")
                ct = resp.headers.get("Content-Type")
                cd = resp.headers.get("Content-Disposition")
                body = b""
                if method == "GET":
                    body = resp.read(120)
                print(
                    f"{method} {resp.status} {url[:110]} "
                    f"ct={ct} cl={cl} cd={cd} body={body[:60]!r}"
                )
                return
        except Exception as exc:  # noqa: BLE001
            print(f"{method} FAIL {url[:110]} -> {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
