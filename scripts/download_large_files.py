"""
Run aria2 large-file downloads for one or more DRPIDs with a quiet console.

Reads ``aria2_inputs/DRP######.cmd`` (from export_usfs_aria2_input.py), runs each
``aria2c`` line with console limited to periodic progress summaries and errors;
full detail is written under ``<base_output_dir>/logs/DRP######/``.

From repo root:

    python scripts/download_large_files.py 29
    scripts\\download_large_files.bat 29 53

Generate missing ``.cmd`` files first:

    python scripts/export_usfs_aria2_input.py --drpids 29
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from collectors.UsfsAria2Export import (  # noqa: E402
    DEFAULT_ARIA2_OUTPUT_DIR,
    aria2_argv_with_quiet_console,
    drpid_cmd_path,
    out_name_from_aria2_argv,
    parse_aria2c_lines_from_cmd_file,
)

DEFAULT_CONFIG_PATH = REPO_ROOT / "config.json"
DEFAULT_SUMMARY_INTERVAL = 60


def load_base_output_dir(config_path: Path) -> Path:
    if config_path.is_file():
        data = json.loads(config_path.read_text(encoding="utf-8"))
        raw = data.get("base_output_dir")
        if raw:
            return Path(raw)
    return Path(r"C:\Documents\DataRescue\USFSData")


def log_path_for_download(log_root: Path, drpid: int, out_name: str) -> Path:
    safe = re.sub(r'[<>:"/\\|?*]', "_", out_name)
    return log_root / f"DRP{drpid:06d}" / f"{safe}.log"


def run_drpid(
    drpid: int,
    *,
    aria2_inputs_dir: Path,
    log_root: Path,
    summary_interval: int,
    stop_on_error: bool,
) -> int:
    cmd_path = drpid_cmd_path(drpid, aria2_inputs_dir)
    if not cmd_path.is_file():
        print(f"ERROR: No batch file at {cmd_path}", file=sys.stderr)
        print(
            "  Generate it with: python scripts/export_usfs_aria2_input.py "
            f"--drpids {drpid}",
            file=sys.stderr,
        )
        return 1

    aria2_lines = parse_aria2c_lines_from_cmd_file(cmd_path)
    if not aria2_lines:
        print(f"DRP {drpid}: no aria2c commands in {cmd_path.name} (nothing to download).")
        return 0

    log_dir = log_root / f"DRP{drpid:06d}"
    log_dir.mkdir(parents=True, exist_ok=True)

    print(f"DRP {drpid}: {len(aria2_lines)} file(s) — logs in {log_dir}")
    print()

    ok_count = 0
    fail_count = 0

    for index, cmd_line in enumerate(aria2_lines, start=1):
        argv_base = shlex.split(cmd_line, posix=False)
        out_name = out_name_from_aria2_argv(argv_base) or f"download_{index}"
        log_path = log_path_for_download(log_root, drpid, out_name)

        print(f"[{index}/{len(aria2_lines)}] {out_name}")
        argv = aria2_argv_with_quiet_console(
            cmd_line,
            log_path=log_path,
            summary_interval=summary_interval,
        )

        result = subprocess.run(argv, check=False)
        if result.returncode == 0:
            ok_count += 1
            print(f"  OK — {out_name}")
        else:
            fail_count += 1
            print(f"  FAILED (exit {result.returncode}) — see {log_path}")
            if stop_on_error:
                break
        print()

    print(f"DRP {drpid} finished: {ok_count} succeeded, {fail_count} failed")
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
        help="config.json for base_output_dir (logs go under base_output_dir/logs)",
    )
    parser.add_argument(
        "--summary-interval",
        type=int,
        default=DEFAULT_SUMMARY_INTERVAL,
        metavar="SEC",
        help=f"Seconds between aria2 progress summaries on console (default: {DEFAULT_SUMMARY_INTERVAL})",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop after the first failed download (default: run all files)",
    )
    args = parser.parse_args()

    base_output = load_base_output_dir(args.config)
    log_root = base_output / "logs"

    exit_code = 0
    for drpid in args.drpids:
        code = run_drpid(
            drpid,
            aria2_inputs_dir=args.aria2_inputs_dir,
            log_root=log_root,
            summary_interval=args.summary_interval,
            stop_on_error=args.stop_on_error,
        )
        if code != 0:
            exit_code = code

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
