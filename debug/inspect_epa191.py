"""Inspect EPA DRPID 191 errors and resource URLs."""

from __future__ import annotations

import re
import sqlite3
import urllib.request
from pathlib import Path


def main() -> None:
    """Print project 191 fields, folder files, and probe readme URL."""
    conn = sqlite3.connect("epa.db")
    cols = [r[1] for r in conn.execute("pragma table_info(projects)")]
    row = conn.execute("select * from projects where DRPID=191").fetchone()
    data = dict(zip(cols, row, strict=True))
    for key in (
        "DRPID",
        "title",
        "status",
        "source_url",
        "folder_path",
        "errors",
        "status_notes",
        "num_files",
        "extensions",
        "file_size",
    ):
        print(f"{key}: {data.get(key)}")
    conn.close()

    folder = Path(str(data.get("folder_path") or ""))
    if folder.is_dir():
        print("\n=== folder ===")
        for path in sorted(folder.iterdir()):
            print(path.name, path.stat().st_size if path.is_file() else "dir")

    source = str(data.get("source_url") or "")
    req = urllib.request.Request(source, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    Path("debug/epa191_catalog.html").write_text(html, encoding="utf-8-sig")
    urls = sorted(set(re.findall(r"https?://[^\s\"'<>]+", html)))
    print("\n=== interesting urls ===")
    for url in urls:
        lower = url.lower()
        if any(
            key in lower
            for key in ("readme", "redme", "download", "zip", "csv", "pdf", "html")
        ):
            print(url)


if __name__ == "__main__":
    main()
