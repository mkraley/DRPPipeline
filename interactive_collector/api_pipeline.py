"""
Flask API for running pipeline modules from the SPA main page.

Exposes: list modules, run a module (subprocess with streamed log output), stop running module.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Generator, Optional

from flask import Blueprint, Response, request

# Project root (parent of interactive_collector)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_MAIN_PY = _PROJECT_ROOT / "main.py"
_STOP_FILE = _PROJECT_ROOT / ".drp_pipeline_stop"

# Current run (so POST /stop can terminate it)
_current_proc: Optional[subprocess.Popen[str]] = None

pipeline_bp = Blueprint("pipeline", __name__, url_prefix="/api/pipeline")


def _modules() -> dict[str, dict[str, Any]]:
    """Return the MODULES registry from the orchestrator."""
    from orchestration.Orchestrator import MODULES
    return dict(MODULES)


@pipeline_bp.route("/modules", methods=["GET"])
def list_modules() -> Any:
    """
    Return the list of pipeline module names (keys of MODULES).

    Returns:
        JSON: { "modules": ["noop", "sourcing", "collector", ...] }
    """
    # Preserve MODULES order (no noop in list for UI)
    mods = [m for m in _modules().keys() if m != "noop"]
    return {"modules": mods}


@pipeline_bp.route("/run", methods=["POST"])
def run_module() -> Any:
    """
    Run a pipeline module in a subprocess and stream its stdout as the response.

    Request JSON: module (required), num_rows (optional), start_drpid (optional),
    log_level (optional), max_workers (optional).

    Returns:
        Streamed text/plain (log output). On invalid input, 400 JSON.
    """
    if not request.is_json:
        data: dict[str, Any] = {}
    else:
        data = request.get_json() or {}

    module = (data.get("module") or "").strip()
    if not module:
        return {"error": "module is required"}, 400

    modules = _modules()
    if module not in modules:
        return {"error": f"Unknown module {module!r}. Valid: {sorted(modules.keys())}"}, 400

    # interactive_collector is not run as subprocess; UI should open collector view instead
    if module == "interactive_collector":
        return {"error": "Use the Interactive Collector button to open the collector UI."}, 400

    num_rows = data.get("num_rows")
    start_drpid = data.get("start_drpid")
    log_level = (data.get("log_level") or "").strip().upper() or None
    max_workers = data.get("max_workers")

    argv = [sys.executable, str(_MAIN_PY), module]
    if num_rows is not None:
        try:
            argv.extend(["--num-rows", str(int(num_rows))])
        except (TypeError, ValueError):
            pass
    if start_drpid is not None:
        try:
            argv.extend(["--start-drpid", str(int(start_drpid))])
        except (TypeError, ValueError):
            pass
    if log_level:
        if log_level in ("DEBUG", "INFO", "WARNING", "ERROR"):
            argv.extend(["--log-level", log_level])
    if max_workers is not None:
        try:
            argv.extend(["--max-workers", str(int(max_workers))])
        except (TypeError, ValueError):
            pass

    def stream() -> Generator[str, None, None]:
        global _current_proc
        proc: Optional[subprocess.Popen[str]] = None
        try:
            # Remove stop file from any previous run; pass path to subprocess so orchestrator can check it
            if _STOP_FILE.exists():
                _STOP_FILE.unlink()
            env = os.environ.copy()
            env["DRP_STOP_FILE"] = str(_STOP_FILE)
            env["PYTHONUNBUFFERED"] = "1"  # So log lines appear in main-page stream immediately
            proc = subprocess.Popen(
                argv,
                cwd=str(_PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
            )
            _current_proc = proc
            assert proc.stdout is not None
            for line in proc.stdout:
                yield line
            proc.wait()
        except Exception as e:
            yield f"\nPipeline run error: {e}\n"
        finally:
            _current_proc = None
            if _STOP_FILE.exists():
                try:
                    _STOP_FILE.unlink()
                except OSError:
                    pass
            if proc is not None and proc.poll() is None:
                proc.terminate()

    return Response(
        stream(),
        mimetype="text/plain; charset=utf-8",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@pipeline_bp.route("/stop", methods=["POST"])
def stop_run() -> Any:
    """
    Request the current pipeline run to stop.

    Writes the stop file (so the orchestrator's inner loop can exit cleanly)
    and terminates the subprocess so work halts promptly.
    """
    global _current_proc
    try:
        _STOP_FILE.touch()
    except OSError:
        pass
    if _current_proc is not None and _current_proc.poll() is None:
        _current_proc.terminate()
    return {"ok": True}
