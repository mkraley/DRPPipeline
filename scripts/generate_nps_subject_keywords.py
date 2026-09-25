"""
Print ICPSR subject keywords for NPS projects from source-page metadata.

Reads project_metadata.json (title, abstract, supplied keywords) plus product
titles. Does not write the database.

    python scripts/generate_nps_subject_keywords.py
    python scripts/generate_nps_subject_keywords.py --drpids 1-7 --db nps.db
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from utils.IcpsrSubjectThesaurus import IcpsrSubjectThesaurus  # noqa: E402
from utils.SubjectKeywordGenerator import SubjectKeywordGenerator, aboutness_text  # noqa: E402

DEFAULT_DB = REPO_ROOT / "nps.db"


def parse_drpids(spec: str) -> list[int]:
    """Parse '1-7' or '1,2,5' into a list of DRPIDs."""
    drpids: list[int] = []
    for part in spec.split(","):
        piece = part.strip()
        if not piece:
            continue
        if "-" in piece:
            start_text, end_text = piece.split("-", 1)
            drpids.extend(range(int(start_text), int(end_text) + 1))
        else:
            drpids.append(int(piece))
    return drpids


def product_titles(connection: sqlite3.Connection, drpid: int) -> list[str]:
    """Return product titles stored for one DRPID."""
    rows = connection.execute(
        "SELECT title FROM nps_products WHERE drpid = ? ORDER BY irma_product_id",
        (drpid,),
    ).fetchall()
    return [str(row[0]) for row in rows if row[0]]


def load_source(folder: Path) -> dict[str, str]:
    """Read title, abstract, and supplied keywords from project_metadata.json."""
    path = folder / "project_metadata.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "title": str(payload.get("title") or ""),
        "abstract": str(payload.get("abstract") or ""),
        "keywords": str(payload.get("keywords") or ""),
    }


def keywords_for_record(
    generator: SubjectKeywordGenerator,
    *,
    title: str,
    abstract: str,
    keywords: str,
    products: list[str],
) -> str:
    """Generate a comma-separated subject string for one project."""
    text = aboutness_text(abstract, keywords, " ".join(products))
    return generator.format_keywords(title, text)


def print_keywords(db_path: Path, drpids: list[int]) -> None:
    """Print supplied keywords and generated ICPSR terms for each DRPID."""
    generator = SubjectKeywordGenerator(IcpsrSubjectThesaurus.load())
    connection = sqlite3.connect(db_path)
    try:
        for drpid in drpids:
            row = connection.execute(
                "SELECT title, keywords, summary, folder_path FROM projects WHERE DRPID = ?",
                (drpid,),
            ).fetchone()
            if row is None:
                print(f"DRPID {drpid}: not found")
                continue
            title, supplied, summary, folder = row
            source = load_source(Path(folder)) if folder else {}
            generated = keywords_for_record(
                generator,
                title=source.get("title") or title or "",
                abstract=source.get("abstract") or summary or "",
                keywords=source.get("keywords") or supplied or "",
                products=product_titles(connection, drpid),
            )
            print(f"DRPID {drpid}: {source.get('title') or title}")
            print(f"  supplied:  {source.get('keywords') or supplied or ''}")
            print(f"  generated: {generated}")
            print()
    finally:
        connection.close()


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Generate ICPSR subject keywords for NPS DRPIDs")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database path")
    parser.add_argument("--drpids", default="1-7", help="DRPID list, e.g. 1-7 or 1,3,5")
    args = parser.parse_args()
    print_keywords(args.db, parse_drpids(args.drpids))


if __name__ == "__main__":
    main()
