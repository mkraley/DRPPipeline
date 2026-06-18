"""
Run aria2 large-file downloads for one or more DRPIDs with minimal console output.

Reads ``aria2_inputs/DRP######.cmd`` (exporting from the catalog automatically when
missing), runs each ``aria2c`` line with in-place progress on one line (like native
aria2), retries failed downloads up to three times (aria2 ``-c`` resumes partial
files), and writes full detail to ``<base_output_dir>/logs/DRP######/``.

From repo root:

    python scripts/download_large_files.py 29
    scripts\\download_large_files.bat 29 53
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from collectors.UsfsAria2Export import (  # noqa: E402
    DEFAULT_ARIA2_MAX_ATTEMPTS,
    DEFAULT_ARIA2_OUTPUT_DIR,
    out_name_from_aria2_cmd_line,
    parse_aria2c_lines_from_cmd_file,
    run_aria2_cmd_line_with_retries,
)
from scripts.export_usfs_aria2_input import (  # noqa: E402
    ensure_drpid_aria2_cmd,
    load_base_output_dir,
    load_db_path,
)
from utils.url_utils import BROWSER_HEADERS  # noqa: E402

DEFAULT_CONFIG_PATH = REPO_ROOT / "config.json"
DEFAULT_SUMMARY_INTERVAL = 0


def log_path_for_download(log_root: Path, drpid: int, out_name: str) -> Path:
    safe = re.sub(r'[<>:"/\\|?*]', "_", out_name)
    return log_root / f"DRP{drpid:06d}" / f"{safe}.log"


def run_drpid(
    drpid: int,
    *,
    conn: sqlite3.Connection,
    aria2_inputs_dir: Path,
    base_output_dir: Path,
    log_root: Path,
    summary_interval: int,
    stop_on_error: bool,
    max_attempts: int,
    min_bytes: int,
    missing_only: bool,
) -> int:
    cmd_path, _ = ensure_drpid_aria2_cmd(
        conn,
        drpid,
        output_dir=aria2_inputs_dir,
        base_output_dir=base_output_dir,
        user_agent=BROWSER_HEADERS["User-Agent"],
        min_bytes=min_bytes,
        missing_only=missing_only,
    )
    if cmd_path is None or not cmd_path.is_file():
        print(f"DRP {drpid}: nothing to download (no large files missing on disk).")
        return 0

    aria2_lines = parse_aria2c_lines_from_cmd_file(cmd_path)
    if not aria2_lines:
        print(f"DRP {drpid}: no aria2c commands in {cmd_path.name} (nothing to download).")
        return 0

    log_dir = log_root / f"DRP{drpid:06d}"
    log_dir.mkdir(parents=True, exist_ok=True)

    ok_count = 0
    fail_count = 0

    for index, cmd_line in enumerate(aria2_lines, start=1):
        out_name = out_name_from_aria2_cmd_line(cmd_line) or f"download_{index}"
        log_path = log_path_for_download(log_root, drpid, out_name)

        if len(aria2_lines) > 1:
            print(f"[{index}/{len(aria2_lines)}] {out_name}", flush=True)

        ok, attempts = run_aria2_cmd_line_with_retries(
            cmd_line,
            log_path=log_path,
            summary_interval=summary_interval,
            max_attempts=max_attempts,
        )
        if ok:
            ok_count += 1
            if attempts > 1:
                print(f"  OK after {attempts} attempt(s)", flush=True)
        else:
            fail_count += 1
            print(
                f"FAILED {out_name} after {attempts} attempt(s) — {log_path}",
                flush=True,
            )
            if stop_on_error:
                break

    if fail_count:
        print(f"DRP {drpid}: {ok_count} ok, {fail_count} failed — logs in {log_dir}", flush=True)
    return 1 if fail_count else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download large USFS files for DRPID(s) using aria2_inputs/*.cmd"
    )
    parser.add_argument(
        "drpids",
        type=int,
        nargs="+",
        help="One or more DRPIDs (e.g. 29 or 9 17 29)",
    )
    parser.add_argument(
        "--aria2-inputs-dir",
        type=Path,
        default=DEFAULT_ARIA2_OUTPUT_DIR,
        help=f"Directory containing DRP######.cmd (default: {DEFAULT_ARIA2_OUTPUT_DIR})",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="config.json for base_output_dir and db_path",
    )
    parser.add_argument(
        "--summary-interval",
        type=int,
        default=DEFAULT_SUMMARY_INTERVAL,
        metavar="SEC",
        help=(
            "If > 0, also print separate progress-summary lines every N seconds "
            f"(default: {DEFAULT_SUMMARY_INTERVAL}, in-place readout only)"
        ),
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop after the first failed download (default: run all files)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_ARIA2_MAX_ATTEMPTS,
        metavar="N",
        help=f"Max aria2 attempts per file on failure (default: {DEFAULT_ARIA2_MAX_ATTEMPTS})",
    )
    parser.add_argument(
        "--min-gb",
        type=float,
        default=1.0,
        help="Minimum catalog size in GB when auto-exporting .cmd (default: 1.0)",
    )
    parser.add_argument(
        "--include-on-disk",
        action="store_true",
        help="When auto-exporting, include large files already on disk",
    )
    args = parser.parse_args()

    if args.max_retries < 1:
        parser.error("--max-retries must be at least 1")

    base_output = load_base_output_dir(args.config)
    log_root = base_output / "logs"
    min_bytes = int(args.min_gb * 1024**3)
    missing_only = not args.include_on_disk

    conn = sqlite3.connect(load_db_path(args.config))
    conn.row_factory = sqlite3.Row

    exit_code = 0
    try:
        for drpid in args.drpids:
            code = run_drpid(
                drpid,
                conn=conn,
                aria2_inputs_dir=args.aria2_inputs_dir,
                base_output_dir=base_output,
                log_root=log_root,
                summary_interval=args.summary_interval,
                stop_on_error=args.stop_on_error,
                max_attempts=args.max_retries,
                min_bytes=min_bytes,
                missing_only=missing_only,
            )
            if code != 0:
                exit_code = code
    finally:
        conn.close()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
