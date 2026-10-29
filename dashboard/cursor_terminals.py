"""
Read Cursor IDE terminal metadata so the dashboard can show shell PIDs.

Cursor writes ``terminals\\{id}.txt`` with YAML frontmatter (``pid``,
``active_command`` / ``last_command``). The dashboard merges that with
Orchestrator run-status files so cards match the PIDs shown in the IDE.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_MAIN_PY_RE = re.compile(r"main\.py\b", re.IGNORECASE)


def cursor_terminals_dir(project_root: Path | None = None) -> Optional[Path]:
    """
    Locate ``.cursor/projects/<slug>/terminals`` for this repo.

    Args:
        project_root: Repo root; defaults to the DRPPipeline root.
    """
    root = (project_root or _PROJECT_ROOT).resolve()
    override = os.environ.get("DRP_TERMINALS_DIR")
    if override:
        path = Path(override)
        return path if path.is_dir() else None
    # c:\\Documents\\Code\\DRPPipeline -> c-Documents-Code-DRPPipeline
    drive = root.drive.rstrip(":").lower()
    rest = root.as_posix()
    if ":" in rest:
        rest = rest.split(":", 1)[1]
    slug = f"{drive}{rest}".replace("/", "-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    path = Path.home() / ".cursor" / "projects" / slug / "terminals"
    return path if path.is_dir() else None


def list_pipeline_terminals(
    terminals_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """
    Return Cursor terminals whose command looks like ``python … main.py …``.

    Args:
        terminals_dir: Override terminals folder (tests).
    """
    directory = terminals_dir if terminals_dir is not None else cursor_terminals_dir()
    if directory is None or not directory.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.txt")):
        record = _parse_terminal_file(path)
        if record is None:
            continue
        command = record.get("command") or ""
        if not _MAIN_PY_RE.search(command):
            continue
        if "dashboard" in command.lower():
            continue
        results.append(record)
    return results


def merge_runs_with_terminals(
    runs: list[dict[str, Any]],
    terminals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Prefer Cursor terminal PIDs on cards; attach unmatched run files after.

    Args:
        runs: From ``RunStatus.list_runs()``.
        terminals: From ``list_pipeline_terminals()``.
    """
    by_terminal = {
        int(run["terminal_pid"]): run
        for run in runs
        if run.get("terminal_pid")
    }
    by_pid = {int(run["pid"]): run for run in runs if run.get("pid")}
    used: set[int] = set()
    merged: list[dict[str, Any]] = []

    for term in terminals:
        term_pid = int(term["pid"])
        run = by_terminal.get(term_pid)
        if run is None:
            run = _match_run_by_module(term, runs, used)
        if run is not None:
            used.add(int(run["pid"]))
            card = dict(run)
            card["terminal_pid"] = term_pid
            card["command_line"] = _display_command(term.get("command") or "")
            if term.get("active"):
                if card.get("status") not in {"running", "stale"}:
                    # Terminal still shows an active command; prefer running label
                    # only when the run file is still active.
                    pass
            elif card.get("status") == "running":
                # Shell finished; keep run-file status (may still be finishing).
                pass
            if not term.get("active") and card.get("status") == "stale":
                card["status"] = "completed"
            merged.append(card)
            continue
        # No run file yet (batch just started, or pre-instrumentation).
        merged.append(_card_from_terminal(term))

    for run in runs:
        if int(run["pid"]) in used:
            continue
        merged.append(run)

    active = [row for row in merged if row.get("status") in {"running", "stale"}]
    finished = [row for row in merged if row.get("status") not in {"running", "stale"}]
    active.sort(key=lambda row: row.get("started_at") or "", reverse=True)
    finished.sort(
        key=lambda row: row.get("ended_at") or row.get("started_at") or "",
        reverse=True,
    )
    return active + finished


def _match_run_by_module(
    term: dict[str, Any],
    runs: list[dict[str, Any]],
    used: set[int],
) -> Optional[dict[str, Any]]:
    """Match a terminal to an unused run with the same module name."""
    module = _module_from_command(term.get("command") or "")
    if not module:
        return None
    active = bool(term.get("active"))
    candidates = [
        run
        for run in runs
        if int(run["pid"]) not in used and run.get("module") == module
    ]
    if active:
        for run in candidates:
            if run.get("status") in {"running", "stale"}:
                return run
    else:
        for run in candidates:
            if run.get("status") not in {"running", "stale"}:
                return run
        for run in candidates:
            if run.get("status") in {"running", "stale"}:
                return run
    return None


def _card_from_terminal(term: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal dashboard card from Cursor terminal metadata alone."""
    command = term.get("command") or ""
    module = _module_from_command(command) or "unknown"
    return {
        "pid": term["pid"],
        "terminal_pid": term["pid"],
        "module": module,
        "command_line": _display_command(command),
        "started_at": None,
        "ended_at": None,
        "status": "running" if term.get("active") else "completed",
        "completed": 0,
        "total": 0,
        "display_index": 0,
        "progress_line": "(waiting for Orchestrator status file)",
        "errors": 0,
        "warnings": 0,
        "last_drpid": None,
    }


def _parse_terminal_file(path: Path) -> Optional[dict[str, Any]]:
    """Parse one Cursor terminal text file into a dict."""
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    try:
        pid = int(meta.get("pid") or "0")
    except ValueError:
        return None
    if pid <= 0:
        return None
    active = meta.get("active_command") or ""
    last = meta.get("last_command") or ""
    command = active or last
    return {
        "pid": pid,
        "active": bool(active),
        "command": command,
        "last_exit_code": meta.get("last_exit_code"),
        "path": str(path),
    }


def _module_from_command(command: str) -> Optional[str]:
    """Extract the pipeline module token after ``main.py``."""
    parts = command.replace("\\", "/").split()
    for index, part in enumerate(parts):
        if part.endswith("main.py") and index + 1 < len(parts):
            candidate = parts[index + 1]
            if not candidate.startswith("-"):
                return candidate
    return None


def _display_command(command: str) -> str:
    """Strip python / main.py prefixes for a short command display."""
    parts = command.split()
    while parts:
        head = Path(parts[0]).name.lower()
        if head in {"python", "python.exe", "py", "py.exe"}:
            parts = parts[1:]
            continue
        if head in {"main.py"}:
            parts = parts[1:]
            continue
        break
    return " ".join(parts) if parts else command
