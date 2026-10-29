"""
Per-process batch run status files for the pipeline dashboard.

Each ``main.py`` Orchestrator batch writes ``debug\\runs\\{pid}.json`` so the
standalone dashboard can show live progress without reading terminal logs.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from utils.windows_process import pid_alive, terminal_pid

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_RUNS_DIR = _PROJECT_ROOT / "debug" / "runs"
_RETENTION = timedelta(hours=24)
# Modules that should not appear on the status dashboard.
_HIDDEN_MODULES = frozenset({"noop", "collect_interactively", "help", "setup"})


class RunStatus:
    """
    Write and list Orchestrator batch status JSON files.

    One active file per process (``{pid}.json``). Methods are process-global;
    use ``runs_dir`` override in tests.
    """

    _lock = threading.Lock()
    _runs_dir: Path = _DEFAULT_RUNS_DIR
    _path: Optional[Path] = None
    _data: dict[str, Any] = {}

    @classmethod
    def set_runs_dir(cls, path: Path) -> None:
        """Override the directory used for status files (tests)."""
        with cls._lock:
            cls._runs_dir = path

    @classmethod
    def reset(cls) -> None:
        """Clear in-memory active-run state (tests)."""
        with cls._lock:
            cls._path = None
            cls._data = {}
            cls._runs_dir = _DEFAULT_RUNS_DIR

    @classmethod
    def tracks_module(cls, module: str) -> bool:
        """
        Return True if this module should appear on the dashboard.

        Hides ``noop``, ``collect_interactively``, ``help``, ``setup``, and
        any module whose name contains ``test``.
        """
        name = (module or "").strip().lower()
        if not name:
            return False
        if name in _HIDDEN_MODULES:
            return False
        if "test" in name:
            return False
        return True

    @classmethod
    def start(
        cls,
        module: str,
        *,
        total: int = 0,
        command_line: Optional[list[str]] = None,
    ) -> None:
        """
        Create a running status file for this process.

        Args:
            module: Orchestrator module name (e.g. ``collect``).
            total: Number of projects in the batch (0 if unknown yet).
            command_line: Optional argv override for tests; otherwise built
                from ``Args`` (not raw ``sys.argv``, which can be polluted).
        """
        if not cls.tracks_module(module):
            return
        pid = os.getpid()
        now = datetime.now().isoformat(timespec="seconds")
        if command_line is not None:
            display_cmd = cls._display_command_line(list(command_line))
        else:
            display_cmd = cls._command_line_from_args(module)
        data: dict[str, Any] = {
            "pid": pid,
            "terminal_pid": terminal_pid(pid),
            "module": module,
            "command_line": display_cmd,
            "started_at": now,
            "ended_at": None,
            "status": "running",
            "completed": 0,
            "total": int(total),
            "display_index": 0,
            "progress_line": cls._initial_progress_line(total),
            "errors": 0,
            "warnings": 0,
            "last_drpid": None,
        }
        path = cls._runs_dir / f"{pid}.json"
        with cls._lock:
            cls._runs_dir.mkdir(parents=True, exist_ok=True)
            cls._path = path
            cls._data = data
            cls._write_unlocked(path, data)

    @classmethod
    def set_total(cls, total: int) -> None:
        """Update the batch total after eligible projects are listed."""
        with cls._lock:
            if not cls._path or not cls._data:
                return
            cls._data["total"] = int(total)
            if not cls._data.get("progress_line") or cls._data["completed"] == 0:
                cls._data["progress_line"] = cls._initial_progress_line(total)
            cls._write_unlocked(cls._path, cls._data)

    @classmethod
    def update_progress(
        cls,
        progress_line: str,
        *,
        display_index: int,
        total: int,
        completed: int,
        errors: int = 0,
        warnings: int = 0,
        last_drpid: Optional[int] = None,
    ) -> None:
        """
        Refresh progress fields from an Orchestrator progress event.

        Args:
            progress_line: Text like ``8/47 projects avg_per_project=… eta=…``.
            display_index: Progress numerator shown in the line.
            total: Batch size.
            completed: Projects finished so far.
            errors: Batch-level error count so far.
            warnings: Batch-level warning count so far.
            last_drpid: Optional last finished DRPID.
        """
        with cls._lock:
            if not cls._path or not cls._data:
                return
            cls._data["progress_line"] = progress_line
            cls._data["display_index"] = int(display_index)
            cls._data["total"] = int(total)
            cls._data["completed"] = int(completed)
            cls._data["errors"] = int(errors)
            cls._data["warnings"] = int(warnings)
            if last_drpid is not None:
                cls._data["last_drpid"] = int(last_drpid)
            cls._write_unlocked(cls._path, cls._data)

    @classmethod
    def finish(
        cls,
        *,
        completed: int,
        errors: int,
        warnings: int,
        status: str,
    ) -> None:
        """
        Mark the active run finished and persist final counters.

        Args:
            completed: Projects finished in the batch.
            errors: Batch-level error count.
            warnings: Batch-level warning count.
            status: ``completed``, ``stopped``, or ``failed``.
        """
        with cls._lock:
            if not cls._path or not cls._data:
                return
            cls._data["completed"] = int(completed)
            cls._data["errors"] = int(errors)
            cls._data["warnings"] = int(warnings)
            cls._data["status"] = status
            cls._data["ended_at"] = datetime.now().isoformat(timespec="seconds")
            cls._write_unlocked(cls._path, cls._data)
            cls._path = None
            cls._data = {}

    @classmethod
    def list_runs(cls, runs_dir: Optional[Path] = None) -> list[dict[str, Any]]:
        """
        Load run files for the dashboard.

        Running files whose PID is dead are reported as ``stale``.
        Finished runs older than 24 hours are omitted.
        Order: running/stale first (newest start), then recent finished.
        """
        directory = runs_dir if runs_dir is not None else cls._runs_dir
        if not directory.is_dir():
            return []
        cutoff = datetime.now() - _RETENTION
        active: list[dict[str, Any]] = []
        finished: list[dict[str, Any]] = []
        for path in directory.glob("*.json"):
            record = cls._read_run_file(path)
            if record is None:
                continue
            module = str(record.get("module") or "")
            if not cls.tracks_module(module):
                continue
            record = cls._normalize_record(record)
            run_pid = int(record.get("pid") or 0)
            if not record.get("terminal_pid") and run_pid:
                record = {**record, "terminal_pid": terminal_pid(run_pid)}
            status = record.get("status")
            if status == "running":
                if not pid_alive(run_pid):
                    # Status file says running, but the OS process is gone.
                    record = {**record, "status": "stale"}
                active.append(record)
                continue
            ended = cls._parse_iso(record.get("ended_at"))
            if ended is not None and ended < cutoff:
                continue
            finished.append(record)
        active.sort(key=lambda r: r.get("started_at") or "", reverse=True)
        finished.sort(key=lambda r: r.get("ended_at") or "", reverse=True)
        return active + finished

    @classmethod
    def _display_command_line(cls, argv: list[str]) -> str:
        """
        Build a short command string, dropping ``python`` / ``main.py`` prefixes.

        Args:
            argv: Process argv list.
        """
        parts = list(argv)
        while parts:
            head = Path(parts[0]).name.lower()
            if head in {"python", "python.exe", "py", "py.exe"}:
                parts = parts[1:]
                continue
            if head in {"main.py"}:
                parts = parts[1:]
                continue
            break
        return " ".join(parts) if parts else " ".join(argv)

    @classmethod
    def _command_line_from_args(cls, module: str) -> str:
        """
        Build the dashboard command from parsed ``Args``, not ``sys.argv``.

        ``sys.argv`` can contain a spurious ``collect_interactively`` token from
        package ``-m`` shims; ``Args.module`` is the authoritative module name.
        """
        parts: list[str] = [module]
        try:
            from utils.Args import Args

            if not getattr(Args, "_initialized", False):
                return module
            parsed = Args.get_args()
        except Exception:
            return module
        flag_map: list[tuple[str, str, bool]] = [
            ("num_rows", "-n", True),
            ("start_drpid", "--start", True),
            ("ids", "--ids", True),
            ("max_workers", "-w", True),
            ("source", "--source", True),
            ("log_level", "--log-level", True),
            ("retry", "--retry", False),
        ]
        for key, flag, takes_value in flag_map:
            if key not in parsed:
                continue
            value = parsed[key]
            if value is None or value is False:
                continue
            if not takes_value:
                parts.append(flag)
                continue
            if key == "ids" and isinstance(value, (list, tuple)):
                parts.extend([flag, ",".join(str(item) for item in value)])
            else:
                parts.extend([flag, str(value)])
        return " ".join(parts)

    @classmethod
    def _normalize_record(cls, record: dict[str, Any]) -> dict[str, Any]:
        """Fix polluted command lines on older run files."""
        module = str(record.get("module") or "")
        cmd = str(record.get("command_line") or "")
        if (
            module
            and module != "collect_interactively"
            and "collect_interactively" in cmd.split()
        ):
            tokens = [
                token
                for token in cmd.split()
                if token not in {"collect_interactively", ".\\main.py", "main.py"}
            ]
            record = {**record, "command_line": " ".join(tokens) or module}
        return record

    @classmethod
    def _initial_progress_line(cls, total: int) -> str:
        """Progress line before any project has finished."""
        return f"0/{int(total)} projects avg_per_project=n/a eta=n/a"

    @classmethod
    def _write_unlocked(cls, path: Path, data: dict[str, Any]) -> None:
        """Atomically write JSON via a same-directory temp file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.stem}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            with open(tmp, "w", encoding="utf-8-sig") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            cls._replace_with_retry(tmp, path)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    @classmethod
    def _replace_with_retry(cls, tmp: Path, path: Path) -> None:
        """Replace ``path`` with ``tmp``, retrying brief Windows file locks."""
        last_error: OSError | None = None
        for attempt in range(8):
            try:
                os.replace(tmp, path)
                return
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.05 * (attempt + 1))
            except OSError as exc:
                last_error = exc
                time.sleep(0.05 * (attempt + 1))
        if last_error is not None:
            raise last_error

    @classmethod
    def _read_run_file(cls, path: Path) -> Optional[dict[str, Any]]:
        """Load one run JSON file, or None if unreadable."""
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                return None
            return data
        except (OSError, json.JSONDecodeError, ValueError):
            return None

    @classmethod
    def _parse_iso(cls, value: Any) -> Optional[datetime]:
        """Parse an ISO timestamp string, or return None."""
        if not value or not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
