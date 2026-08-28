"""
Audit published DataLumos view pages for filenames truncated by legacy limits.

Scans published project views (e.g.
``/datalumos/project/250591/version/V1/view``) and flags filenames that are
exactly 100 characters (legacy ADC/USFS sanitize default) or exactly 80
(legacy interactive collector). Optionally cross-checks catalog names from
Figshare (ADC) or the USFS Research Data Archive catalog HTML.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_argv_backup = sys.argv[:]
sys.argv = [_argv_backup[0], "upload"]
from utils.Args import Args  # noqa: E402
from utils.Logger import Logger  # noqa: E402

Args.initialize()
sys.argv = _argv_backup
Logger.initialize(log_level="INFO")

from sourcing.AdcApiClient import AdcApiClient, article_id_from_source_url  # noqa: E402
from upload.DataLumosBrowserSession import DataLumosBrowserSession  # noqa: E402
from upload.DataLumosAuthenticator import wait_for_human_verification  # noqa: E402
from verify.DatalumosViewFileStats import (  # noqa: E402
    DatalumosViewFileStats,
    set_records_per_page,
)

LEGACY_ADC_LIMIT = 100
LEGACY_INTERACTIVE_LIMIT = 80
PUBLISHED_VIEW_URL_TEMPLATE = (
    "https://www.datalumos.org/datalumos/project/{datalumos_id}/version/V1/view"
)


def _legacy_sanitize_no_extension_preserve(name: str, max_length: int) -> str:
    """Old sanitize_filename behavior (blind truncate, no extension preserve)."""
    import re
    import unicodedata

    if not name:
        return "Untitled"
    sanitized = unicodedata.normalize("NFKD", str(name))
    replacements = {
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201C": '"',
        "\u201D": '"',
        "\u2026": "...",
        "\u00A0": " ",
    }
    for old_char, new_char in replacements.items():
        sanitized = sanitized.replace(old_char, new_char)
    sanitized = re.sub(r'[<>:"/\\|?*]', "_", sanitized)
    sanitized = re.sub(r"[\x00-\x1f\x7f]", "", sanitized)
    sanitized = sanitized.encode("ascii", errors="replace").decode("ascii").replace("?", "_")
    sanitized = sanitized.strip(". ")
    sanitized = re.sub(r"[_\s]+", "_", sanitized).strip("_")
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].strip(". _")
    return sanitized or "Untitled"


def _has_likely_extension(name: str) -> bool:
    """Return True when the basename ends with a dotted extension segment."""
    if "." not in name:
        return False
    ext_part = name.rsplit(".", 1)[-1]
    return bool(ext_part) and len(ext_part) <= 10 and ext_part.isalnum()


def _suspicious_lengths(name: str) -> list[int]:
    """Return legacy limits matched by exact name length."""
    length = len(name)
    hits: list[int] = []
    if length == LEGACY_ADC_LIMIT:
        hits.append(LEGACY_ADC_LIMIT)
    if length == LEGACY_INTERACTIVE_LIMIT:
        hits.append(LEGACY_INTERACTIVE_LIMIT)
    return hits


def _published_view_url(project: dict[str, Any]) -> str:
    """Resolve the published view URL for a project row."""
    published = str(project.get("published_url") or "").strip()
    if published:
        return published
    datalumos_id = str(project["datalumos_id"]).strip()
    return PUBLISHED_VIEW_URL_TEMPLATE.format(datalumos_id=datalumos_id)


def _adc_catalog_names(source_url: str, api: AdcApiClient) -> list[str]:
    """Fetch Figshare-hosted file names for an ADC source URL."""
    article_id = article_id_from_source_url(source_url)
    if article_id is None:
        return []
    article = api.fetch_article(article_id)
    return [
        str(file_obj.get("name") or "")
        for file_obj in (article.get("files") or [])
        if isinstance(file_obj, dict) and file_obj.get("name")
    ]


def _usfs_catalog_names(source_url: str, page: Any | None = None) -> list[str]:
    """Fetch USFS catalog publication file names for a source URL."""
    from verify.MissingFileRepair import fetch_catalog_publication_files

    publication_files = fetch_catalog_publication_files(source_url, page=page)
    return [filename for filename, _, _ in publication_files if filename]


def _fetch_catalog_names(
    source_url: str,
    catalog_source: str,
    *,
    api: AdcApiClient | None,
    page: Any | None = None,
) -> list[str]:
    """
    Return catalog filenames for cross-checking truncated DataLumos names.

    Args:
        source_url: Project catalog URL from Storage.
        catalog_source: ``adc``, ``usfs``, or ``none``.
        api: Figshare client (required for ``adc``).
        page: Optional Playwright page for USFS catalog browser fallback.

    Returns:
        Original catalog filenames.
    """
    if catalog_source == "none" or not source_url:
        return []
    if catalog_source == "usfs":
        return _usfs_catalog_names(source_url, page=page)
    if api is None:
        return []
    return _adc_catalog_names(source_url, api)


def _match_catalog_name(dl_name: str, catalog_names: list[str]) -> str | None:
    """Return catalog original when dl_name equals legacy 100-char sanitize."""
    dl_key = dl_name.casefold()
    for original in catalog_names:
        if not original:
            continue
        legacy = _legacy_sanitize_no_extension_preserve(original, LEGACY_ADC_LIMIT)
        if legacy.casefold() == dl_key:
            return original
    return None


def _resolve_catalog_source(db_path: str, explicit: str) -> str:
    """Choose ADC vs USFS catalog lookup from CLI flag or database filename."""
    if explicit != "auto":
        return explicit
    if "usfs" in Path(db_path).name.lower():
        return "usfs"
    return "adc"


def _default_output_path(db_path: str) -> Path:
    """Default CSV path based on the database being scanned."""
    if "usfs" in Path(db_path).name.lower():
        return Path("debug") / "usfs_datalumos_truncated_filenames.csv"
    return Path("debug") / "datalumos_truncated_filenames.csv"


def _load_projects(
    *,
    db_path: str | None,
    start_drpid: int | None,
    limit: int | None,
    drpid: int | None,
) -> list[dict[str, Any]]:
    """Load projects with DataLumos IDs from the SQLite database."""
    path = Path(db_path or "adc.db")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    query = """
        SELECT DRPID, datalumos_id, published_url, source_url, title
        FROM projects
        WHERE datalumos_id IS NOT NULL AND TRIM(datalumos_id) <> ''
    """
    params: list[Any] = []
    if drpid is not None:
        query += " AND DRPID = ?"
        params.append(drpid)
    elif start_drpid is not None:
        query += " AND DRPID >= ?"
        params.append(start_drpid)
    query += " ORDER BY DRPID"
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    rows = [dict(row) for row in conn.execute(query, params).fetchall()]
    conn.close()
    return rows


def _read_published_file_names(page: Any, published_url: str) -> tuple[list[str], str | None]:
    """
    Navigate to a published view and return filenames listed there.

    Returns:
        ``(file_names, error_message)`` where error is set only when no names found.
    """
    page.goto(published_url, wait_until="load", timeout=120000)
    wait_for_human_verification(page, timeout=60000)
    set_records_per_page(page, page_size=100)
    stats = DatalumosViewFileStats.from_page(page)
    file_names = list(stats.file_names)
    if file_names:
        return file_names, stats.error
    return [], stats.error or "no_files_found"


def audit_projects(
    projects: list[dict[str, Any]],
    *,
    catalog_source: str,
    delay_sec: float,
    output_path: Path,
) -> list[dict[str, str]]:
    """
    Scan published DataLumos view file names for truncation signals.

    Returns:
        CSV row dicts for suspicious filenames.
    """
    session = DataLumosBrowserSession()
    page = session.ensure_browser()
    session.ensure_authenticated()
    api = AdcApiClient(request_delay=0.15) if catalog_source == "adc" else None
    findings: list[dict[str, str]] = []
    fieldnames = [
        "drpid",
        "datalumos_id",
        "filename",
        "name_length",
        "matched_limits",
        "missing_extension",
        "catalog_original",
        "title",
        "published_url",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for index, project in enumerate(projects, start=1):
            drpid = int(project["DRPID"])
            datalumos_id = str(project["datalumos_id"]).strip()
            source_url = str(project.get("source_url") or "").strip()
            title = str(project.get("title") or "").strip()
            published_url = _published_view_url(project)
            Logger.info(
                "Scanning DRPID %s (DL %s) [%s/%s]",
                drpid,
                datalumos_id,
                index,
                len(projects),
            )

            try:
                file_names, read_error = _read_published_file_names(page, published_url)
            except Exception as exc:
                Logger.warning("DRPID %s: page read failed: %s", drpid, exc)
                time.sleep(delay_sec)
                continue

            if read_error and not file_names:
                Logger.warning("DRPID %s: could not read files: %s", drpid, read_error)
                time.sleep(delay_sec)
                continue
            if read_error:
                Logger.warning(
                    "DRPID %s: partial file list (%s): %s",
                    drpid,
                    len(file_names),
                    read_error,
                )

            catalog_names: list[str] = []
            if catalog_source != "none" and source_url:
                try:
                    catalog_names = _fetch_catalog_names(
                        source_url,
                        catalog_source,
                        api=api,
                        page=page,
                    )
                except Exception as exc:
                    Logger.warning("DRPID %s: catalog fetch failed: %s", drpid, exc)

            for name in file_names:
                limits = _suspicious_lengths(name)
                if not limits:
                    continue
                row = {
                    "drpid": str(drpid),
                    "datalumos_id": datalumos_id,
                    "filename": name,
                    "name_length": str(len(name)),
                    "matched_limits": ",".join(str(value) for value in limits),
                    "missing_extension": str(not _has_likely_extension(name)),
                    "catalog_original": (
                        _match_catalog_name(name, catalog_names) if catalog_names else ""
                    ),
                    "title": title[:120],
                    "published_url": published_url,
                }
                findings.append(row)
                writer.writerow(row)
                handle.flush()

            time.sleep(delay_sec)

    session.close()
    return findings


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default="adc.db", help="SQLite database path")
    parser.add_argument("--drpid", type=int, help="Audit a single DRPID")
    parser.add_argument("--start-drpid", type=int, help="Minimum DRPID")
    parser.add_argument("-n", "--limit", type=int, help="Max projects to scan")
    parser.add_argument(
        "--catalog-source",
        choices=("auto", "adc", "usfs", "none"),
        default="auto",
        help="Catalog cross-check: auto (from db filename), adc, usfs, or none",
    )
    parser.add_argument(
        "--no-catalog",
        action="store_true",
        help="Deprecated alias for --catalog-source none",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="CSV output path (default: debug/*_truncated_filenames.csv by db)",
    )
    parser.add_argument("--delay", type=float, default=0.3, help="Delay between projects")
    args = parser.parse_args()

    catalog_source = "none" if args.no_catalog else _resolve_catalog_source(
        args.db_path, args.catalog_source
    )
    output_path = args.output or _default_output_path(args.db_path)

    projects = _load_projects(
        db_path=args.db_path,
        start_drpid=args.start_drpid,
        limit=args.limit,
        drpid=args.drpid,
    )
    if not projects:
        print("No projects matched.")
        return

    findings = audit_projects(
        projects,
        catalog_source=catalog_source,
        delay_sec=args.delay,
        output_path=output_path,
    )

    print(f"Scanned {len(projects)} project(s); {len(findings)} suspicious filename(s).")
    print(f"Catalog source: {catalog_source}")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
