"""Inspect EPA DRPID 29 and related resource URLs."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def main() -> None:
    """Print project 29 fields and any resource-like tables."""
    db = Path(__file__).resolve().parents[1] / "epa.db"
    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("pragma table_info(projects)")]
    row = conn.execute("select * from projects where DRPID=29").fetchone()
    if not row:
        print("DRPID 29 not found")
        return
    data = dict(zip(cols, row, strict=True))
    for key in (
        "DRPID",
        "title",
        "status",
        "next_step",
        "source_url",
        "folder_path",
        "status_notes",
        "warnings",
        "errors",
        "collection_notes",
        "summary",
        "extensions",
        "data_types",
    ):
        print(f"{key}: {data.get(key)}")
    print("--- tables ---")
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    ]
    print(tables)
    for table in tables:
        if table == "projects":
            continue
        info = list(conn.execute(f"pragma table_info({table})"))
        col_names = [c[1] for c in info]
        if "DRPID" in col_names:
            rows = conn.execute(
                f"select * from {table} where DRPID=29"
            ).fetchall()
            if rows:
                print(f"--- {table} ---")
                print(col_names)
                for r in rows:
                    print(r)
    conn.close()


if __name__ == "__main__":
    main()
