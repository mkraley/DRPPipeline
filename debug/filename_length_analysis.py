"""Analyze filename length distribution and path budget."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from utils.file_utils import sanitize_filename

BASE = Path(r"C:\DataRescue\AHRQData")
FOLDER = "AHRQ000430"
PREFIX_LEN = len(str(BASE / FOLDER)) + 1  # +1 for trailing backslash before filename

LIMITS = (80, 100, 150, 200, 224, 255)


def path_budget(base: Path, folder: str) -> int:
    """Remaining chars for filename under legacy MAX_PATH (260)."""
    prefix = len(str(base / folder)) + 1
    return max(0, 260 - prefix)


def main() -> None:
    print(f"Example base path: {BASE / FOLDER}\\")
    print(f"Prefix length: {PREFIX_LEN}, MAX_PATH budget for filename: {path_budget(BASE, FOLDER)}")
    print()

    db = Path("adc.db")
    if db.exists():
        conn = sqlite3.connect(db)
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        print("adc.db tables:", [r[0] for r in rows])
        conn.close()

    # Hunter case
    hunter = (
        "Hunter_2012. History of Early Contributions Homalodisca coagulata "
        "(Glassy-winged sharpshooter) ESTs, Transcriptome, Micrbiome.docx"
    )
    full = sanitize_filename(hunter, max_length=10000)
    print(f"\nHunter sanitized full length: {len(full)}")
    for lim in LIMITS:
        s = sanitize_filename(hunter, max_length=lim)
        print(f"  limit {lim:3d}: len={len(s):3d}, changed={s != full}")


if __name__ == "__main__":
    main()
