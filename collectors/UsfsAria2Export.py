"""
Build Windows aria2c command files for large USFS publication downloads.

Used by UsfsCollector when files are skipped (>1 GB) and by
scripts/export_usfs_aria2_input.py for batch export.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from utils.file_utils import sanitize_filename
from utils.url_utils import BROWSER_HEADERS

PublicationFile = Tuple[str, str, Optional[int]]
MAX_DOWNLOAD_BYTES = 1 * 1024**3  # match UsfsCollector.MAX_DOWNLOAD_BYTES

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARIA2_OUTPUT_DIR = REPO_ROOT / "aria2_inputs"


@dataclass(frozen=True)
class Aria2Entry:
    """One publication file to download with aria2c."""

    url: str
    out_name: str
    dir_path: Path
    max_connections: int


def _cmd_quote(value: str) -> str:
    """Quote a value for Windows cmd.exe (double quotes, escape embedded quotes)."""
    return '"' + value.replace('"', '""') + '"'


def max_connections_for_url(url: str) -> int:
    """Box shared links tolerate more connections than USDA product URLs."""
    host = (urlparse(url).hostname or "").lower()
    if "box.com" in host:
        return 16
    if host.endswith("fs.usda.gov"):
        return 4
    return 8


def entries_for_publication_files(
    publication_files: Sequence[PublicationFile],
    folder_path: Path,
    *,
    min_bytes: int = MAX_DOWNLOAD_BYTES,
    missing_only: bool = True,
) -> List[Aria2Entry]:
    """
    Build aria2 entries for publication files at or above ``min_bytes``.

    Skips files already on disk when ``missing_only`` is True.
    """
    entries: List[Aria2Entry] = []
    for filename, file_url, catalog_bytes in publication_files:
        if catalog_bytes is None or catalog_bytes < min_bytes:
            continue
        out_name = sanitize_filename(filename)
        dest = folder_path / out_name
        if missing_only and dest.is_file():
            continue
        entries.append(
            Aria2Entry(
                url=file_url,
                out_name=out_name,
                dir_path=folder_path.resolve(),
                max_connections=max_connections_for_url(file_url),
            )
        )
    return entries


def parse_aria2c_lines_from_cmd_text(text: str) -> List[str]:
    """Return bare ``aria2c ...`` command lines from a Windows ``.cmd`` batch file."""
    lines: List[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.lower().startswith("aria2c "):
            lines.append(stripped)
    return lines


def parse_aria2c_lines_from_cmd_file(cmd_path: Path) -> List[str]:
    """Load ``aria2c`` command lines from ``DRP######.cmd``."""
    return parse_aria2c_lines_from_cmd_text(cmd_path.read_text(encoding="utf-8"))


_ARIA2_OUT_NAME_RE = re.compile(r'-o\s+"([^"]+)"', re.IGNORECASE)
_CMD_QUOTED_VALUE = r'"((?:[^"]|"")*)"'


def _unquote_cmd_value(value: str) -> str:
    return value.replace('""', '"')


def out_name_from_aria2_cmd_line(cmd_line: str) -> Optional[str]:
    """Extract ``-o`` output filename from a Windows ``aria2c`` command line."""
    match = _ARIA2_OUT_NAME_RE.search(cmd_line)
    if match:
        return match.group(1)
    return None


def parse_aria2_windows_cmd_line(cmd_line: str) -> List[str]:
    """
    Parse a Windows ``aria2c`` command line from our ``.cmd`` export format.

    Handles quoted values and parentheses in ``--user-agent`` without using
    ``shlex`` (which breaks on Windows for User-Agent strings).
    """
    stripped = cmd_line.strip()
    if not stripped.lower().startswith("aria2c"):
        raise ValueError(f"Not an aria2c command: {cmd_line[:80]!r}")

    rest = stripped[6:].lstrip()
    argv: List[str] = ["aria2c"]

    ua_match = re.search(r"--user-agent=" + _CMD_QUOTED_VALUE, rest)
    if not ua_match:
        raise ValueError(f"Missing --user-agent in aria2 command: {cmd_line[:80]!r}")

    prefix = rest[: ua_match.start()].strip()
    if prefix:
        argv.extend(prefix.split())

    argv.append("--user-agent=" + _unquote_cmd_value(ua_match.group(1)))
    tail = rest[ua_match.end() :].strip()

    for flag in ("-d", "-o"):
        match = re.match(rf"{re.escape(flag)}\s+" + _CMD_QUOTED_VALUE, tail)
        if not match:
            raise ValueError(f"Missing {flag} in aria2 command: {cmd_line[:80]!r}")
        argv.extend([flag, _unquote_cmd_value(match.group(1))])
        tail = tail[match.end() :].strip()

    url_match = re.match(_CMD_QUOTED_VALUE, tail)
    if not url_match:
        raise ValueError(f"Missing download URL in aria2 command: {cmd_line[:80]!r}")
    argv.append(_unquote_cmd_value(url_match.group(1)))

    return argv


def aria2_argv_for_download(
    cmd_line: str,
    *,
    log_path: Path,
    summary_interval: int = 0,
) -> List[str]:
    """
    Build argv for ``subprocess`` to run an exported ``aria2c`` download.

    Console: in-place progress readout (like native aria2), final download-result
    line on completion, errors/warnings only besides that. Full detail goes to
    ``log_path``.

    ``summary_interval`` > 0 also prints separate progress-summary lines every N
    seconds (usually redundant with the readout); default 0 disables those.
    """
    argv = parse_aria2_windows_cmd_line(cmd_line)
    extras = [
        "--console-log-level=warn",
        f"--summary-interval={summary_interval}",
        f"--log={log_path}",
        "--log-level=notice",
        "--show-console-readout=true",
    ]
    return [argv[0], *extras, *argv[1:]]


def drpid_cmd_path(drpid: int, output_dir: Path | None = None) -> Path:
    """Path to ``aria2_inputs/DRP######.cmd`` for a DRPID."""
    out_dir = output_dir or DEFAULT_ARIA2_OUTPUT_DIR
    return out_dir / f"DRP{drpid:06d}.cmd"


def format_windows_command(entry: Aria2Entry, user_agent: str) -> str:
    """One complete aria2c command line for cmd.exe (copy-paste or .cmd batch)."""
    conn = entry.max_connections
    ua = _cmd_quote(user_agent)
    dest_dir = _cmd_quote(str(entry.dir_path))
    out_name = _cmd_quote(entry.out_name)
    url = _cmd_quote(entry.url)
    return (
        f"aria2c -c -x {conn} -s {conn} -j 1 --file-allocation=none "
        f"--max-tries=0 --retry-wait=10 --user-agent={ua} "
        f"-d {dest_dir} -o {out_name} {url}"
    )


def format_windows_commands(
    entries: Iterable[Aria2Entry],
    user_agent: str,
    *,
    drpid: int | None = None,
) -> str:
    """Format entries as a runnable Windows .cmd batch file."""
    entry_list = list(entries)
    if not entry_list:
        return ""

    lines = ["@echo off", "setlocal"]
    if drpid is not None:
        lines.append(f"REM DRPID {drpid} — large USFS publication downloads")
    lines.append("")

    for entry in entry_list:
        lines.append(f"echo Downloading {entry.out_name} ...")
        lines.append(format_windows_command(entry, user_agent))
        lines.append("if errorlevel 1 exit /b 1")
        lines.append("")

    lines.append("echo Done.")
    return "\n".join(lines) + "\n"


def write_drpid_aria2_cmd(
    drpid: int,
    folder_path: Path,
    publication_files: Sequence[PublicationFile],
    *,
    output_dir: Path | None = None,
    min_bytes: int = MAX_DOWNLOAD_BYTES,
    missing_only: bool = True,
    user_agent: str | None = None,
) -> Path | None:
    """
    Write ``DRP######.cmd`` for missing large publication files.

    Returns the path written, or None if there was nothing to export.
    """
    entries = entries_for_publication_files(
        publication_files,
        folder_path,
        min_bytes=min_bytes,
        missing_only=missing_only,
    )
    if not entries:
        return None

    out_dir = output_dir or DEFAULT_ARIA2_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"DRP{drpid:06d}.cmd"
    ua = user_agent or BROWSER_HEADERS["User-Agent"]
    out_path.write_text(format_windows_commands(entries, ua, drpid=drpid), encoding="utf-8")
    return out_path
