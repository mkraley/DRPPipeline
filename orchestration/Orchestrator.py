"""
Orchestrator for DRP Pipeline.

Central loop: list_eligible_projects and run() only here. Resolves module
from MODULES registry, dynamically imports module classes by name, and calls run(drpid).
"""

import importlib
import logging
import pkgutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from storage import Storage
from utils.Args import Args
from utils.Errors import record_crash, record_error
from utils.Logger import Logger


# Registry mapping module names to their class names and prerequisites
MODULES: Dict[str, Dict[str, Any]] = {
    "noop": {
        "prereq": None,
        "class_name": None,  # Handled directly in Orchestrator
    },
    "sourcing": {
        "prereq": None,
        "class_name": "Sourcing",
    },
    "interactive_collector": {
        "prereq": "sourced",
        "class_name": None,  # Handled directly: start Flask app with first eligible URL
    },
    "socrata_collector": {
        "prereq": "sourced",
        "class_name": "SocrataCollector",  
    },
    "catalog_collector": {
        "prereq": "sourced",
        "class_name": "CatalogDataCollector",
    },
    "cms_collector": {
        "prereq": "sourced",
        "class_name": "CmsGovCollector",
    },
    "usfs_collector": {
        "prereq": "sourced",
        "class_name": "UsfsCollector",
    },
    "upload": {
        "prereq": "collected",
        "class_name": "DataLumosUploader",
    },
    "publisher": {
        "prereq": "uploaded",
        "class_name": "DataLumosPublisher",
    },
    "cleanup_inprogress": {
        "prereq": None,
        "class_name": "CleanupInProgress",
    },
    "setup": {
        "prereq": None,
        "class_name": "Setup",
    },

}


def _find_module_class(class_name: str) -> type:
    """
    Dynamically find and import a module class by name.
    
    Searches the entire project tree from the root using pkgutil.walk_packages,
    looking for the class in any Python module.
    
    Args:
        class_name: Name of the class (e.g., "Sourcing", "SocrataCollector")
        
    Returns:
        The module class
        
    Raises:
        ImportError: If the class cannot be found or imported
    """
    # Get project root (directory containing main.py/orchestration)
    project_root = Path(__file__).parent.parent
    project_root_str = str(project_root)
    
    # Ensure project root is on sys.path for pkgutil
    was_on_path = project_root_str in sys.path
    if not was_on_path:
        sys.path.insert(0, project_root_str)
    
    try:
        # Walk through all packages and modules in the project
        for importer, modname, ispkg in pkgutil.walk_packages([project_root_str]):
            # Skip test modules
            if "test" in modname.lower():
                continue
            
            try:
                # Import the module
                module = importlib.import_module(modname)
                # Check if it has the class we're looking for
                if hasattr(module, class_name):
                    cls = getattr(module, class_name)
                    # Verify it's actually a class
                    if isinstance(cls, type):
                        return cls
            except (ImportError, AttributeError, TypeError):
                # Skip modules that can't be imported or don't have the class
                continue
    finally:
        # Clean up: remove from sys.path if we added it
        if not was_on_path and project_root_str in sys.path:
            sys.path.remove(project_root_str)
    
    record_crash(
        f"Could not find module class '{class_name}' in project tree."
    )


def _stop_requested() -> bool:
    """Return True if the GUI requested stop (stop file exists)."""
    stop_file = getattr(Args, "stop_file", None)
    if not stop_file:
        return False
    path = Path(stop_file) if isinstance(stop_file, str) else stop_file
    return path.exists()


class _BatchLevelCounter(logging.Filter):
    """Count WARNING and ERROR log records during an orchestration batch."""

    def __init__(self) -> None:
        super().__init__()
        self.errors = 0
        self.warnings = 0
        self._lock = threading.Lock()

    def filter(self, record: logging.LogRecord) -> bool:
        with self._lock:
            if record.levelno >= logging.ERROR:
                self.errors += 1
            elif record.levelno >= logging.WARNING:
                self.warnings += 1
        return True


@dataclass
class _BatchStats:
    module: str
    counter: _BatchLevelCounter
    projects_completed: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def note_project_finished(self) -> None:
        with self._lock:
            self.projects_completed += 1


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {secs:.1f}s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h {int(minutes)}m {secs:.1f}s"


def _log_batch_summary(stats: _BatchStats, elapsed: float) -> None:
    completed = stats.projects_completed
    errors = stats.counter.errors
    warnings = stats.counter.warnings
    avg_str = _format_duration(elapsed / completed) if completed else "n/a"
    Logger.info(
        f"Orchestrator batch summary module={stats.module!r} "
        f"completed={completed} errors={errors} warnings={warnings} "
        f"elapsed={_format_duration(elapsed)} avg_per_project={avg_str}"
    )


@contextmanager
def _orchestration_batch(module: str) -> Iterator[_BatchStats]:
    counter = _BatchLevelCounter()
    Logger.get_logger().addFilter(counter)
    stats = _BatchStats(module=module, counter=counter)
    start = time.perf_counter()
    try:
        yield stats
    finally:
        Logger.get_logger().removeFilter(counter)
        _log_batch_summary(stats, time.perf_counter() - start)


class Orchestrator:
    """
    Runs a single module (sourcing, collectors, etc.) on projects.

    For modules with no prereq (sourcing): calls run(-1) once.
    For modules with prereq: list_eligible_projects(prereq, num_rows), then calls run(drpid) for each.
    """

    @classmethod
    def run(cls, module: str) -> None:
        """
        Run the named module. Dynamically loads the module class and calls run(drpid).

        Args:
            module: Module name (e.g. "sourcing", "collectors").

        Raises:
            ValueError: If module is not in MODULES.
            ImportError: If the module class cannot be imported.
        """
        if module not in MODULES:
            valid = ", ".join(sorted(MODULES.keys()))
            raise ValueError(f"Unknown module {module!r}. Valid: {valid}")
        
        info = MODULES[module]
        prereq = info["prereq"]
        class_name = info["class_name"]
        
        # Initialize storage
        Storage.initialize(Args.storage_implementation, db_path=Path(Args.db_path))

        # Only sourcing may wipe the DB, and only when delete_all_db_entries is true in config and/or CLI
        # (default false — omit both and the database is left intact).
        if module == "sourcing" and bool(Args.delete_all_db_entries):
            Logger.warning(
                "Deleting all database entries before sourcing (delete_all_db_entries in config and/or "
                "--delete-all-db-entries on command line)"
            )
            Storage.clear_all_records()
        
        num_rows: Optional[int] = Args.num_rows
        start_row: Optional[int] = Args.start_row
        start_drpid: Optional[int] = getattr(Args, "start_drpid", None)
        Logger.info(f"Orchestrator running module={module!r} num_rows={num_rows} start_row={start_row} start_drpid={start_drpid}")
        
        # Handle noop directly
        if module == "noop":
            Logger.info(f"Orchestrator finished module={module!r}")
            return

        # Handle interactive_collector: set DB path and start Flask app (app loads first eligible from Storage)
        if module == "interactive_collector":
            from interactive_collector.app import app as interactive_app
            Logger.info("Starting interactive collector (open http://127.0.0.1:5000/)")
            interactive_app.run(host="127.0.0.1", port=5000, debug=False)
            Logger.info(f"Orchestrator finished module={module!r}")
            return

        # Load and instantiate module class
        module_class = _find_module_class(class_name)
        module_instance = module_class()
        Logger.debug(f"Orchestrator loaded module class={class_name!r}")

        if prereq is None:
            with _orchestration_batch(module) as batch:
                module_instance.run(-1)
                batch.note_project_finished()
        else:
            # Modules with prereq: call run(drpid) for each eligible project
            if module == "publisher":
                # Publisher also processes not_found and no_links (sheet-only update)
                projects_upload = Storage.list_eligible_projects("uploaded", num_rows, start_row, start_drpid)
                projects_not_found = Storage.list_eligible_projects("not_found", num_rows, start_row, start_drpid)
                projects_no_links = Storage.list_eligible_projects("no_links", num_rows, start_row, start_drpid)
                seen: set[int] = set()
                projects = []
                for proj in projects_upload + projects_not_found + projects_no_links:
                    drpid = proj["DRPID"]
                    if drpid not in seen:
                        seen.add(drpid)
                        projects.append(proj)
                projects.sort(key=lambda p: p["DRPID"])
                if num_rows is not None:
                    projects = projects[:num_rows]
            elif module == "upload":
                projects_collected = Storage.list_eligible_projects(
                    "collected", num_rows, start_row, start_drpid
                )
                projects_large = Storage.list_eligible_projects(
                    "collected - large file", num_rows, start_row, start_drpid
                )
                seen_upload: set[int] = set()
                projects = []
                for proj in projects_collected + projects_large:
                    drpid = proj["DRPID"]
                    if drpid not in seen_upload:
                        seen_upload.add(drpid)
                        projects.append(proj)
                projects.sort(key=lambda p: p["DRPID"])
                if num_rows is not None:
                    projects = projects[:num_rows]
            else:
                Logger.info(f"Orchestrator listing eligible projects prereq={prereq!r}")
                projects = Storage.list_eligible_projects(prereq, num_rows, start_row, start_drpid)
            Logger.info(f"Orchestrator module={module!r} eligible projects={len(projects)}")
            max_workers = Args.max_workers or 1
            max_workers = max(1, int(max_workers))

            with _orchestration_batch(module) as batch:
                def run_one(proj: Dict[str, Any]) -> None:
                    drpid = proj["DRPID"]
                    source_url = proj.get("source_url", "")
                    Logger.set_current_drpid(drpid)
                    # Each thread gets its own module instance (and thus its own Playwright/browser)
                    instance = module_class()
                    try:
                        Logger.info(
                            f"Orchestrator starting project module={module!r} "
                            f"DRPID={drpid} source_url={source_url!r}"
                        )
                        instance.run(drpid)
                    except Exception as exc:
                        record_error(
                            drpid,
                            f"Orchestrator module={module!r} DRPID={drpid} exception: {exc}",
                        )
                    finally:
                        batch.note_project_finished()
                        Logger.info(
                            f"Orchestrator finished project module={module!r} DRPID={drpid}"
                        )
                        Logger.clear_current_drpid()

                n_projects = len(projects)
                if max_workers <= 1:
                    # Single-threaded: reuse one instance
                    for idx, proj in enumerate(projects, 1):
                        if _stop_requested():
                            Logger.info("Orchestrator stopped by user (stop file)")
                            return
                        Logger.info(f"Orchestrator progress: {idx}/{n_projects} projects")
                        drpid = proj["DRPID"]
                        source_url = proj.get("source_url", "")
                        Logger.set_current_drpid(drpid)
                        try:
                            Logger.info(
                                f"Orchestrator starting project module={module!r} "
                                f"DRPID={drpid} ({idx}/{n_projects}) source_url={source_url!r}"
                            )
                            module_instance.run(drpid)
                        except Exception as exc:
                            record_error(
                                drpid,
                                f"Orchestrator module={module!r} DRPID={drpid} exception: {exc}",
                            )
                        finally:
                            batch.note_project_finished()
                            Logger.info(
                                f"Orchestrator finished project module={module!r} "
                                f"DRPID={drpid} ({idx}/{n_projects})"
                            )
                            Logger.clear_current_drpid()
                else:
                    Logger.info(f"Orchestrator running with max_workers={max_workers}")
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        futures = {executor.submit(run_one, proj): proj for proj in projects}
                        done = 0
                        for future in as_completed(futures):
                            if _stop_requested():
                                Logger.info("Orchestrator stopped by user (stop file)")
                                # Shutdown cancels remaining futures
                                executor.shutdown(wait=False, cancel_futures=True)
                                return
                            done += 1
                            if n_projects <= 20 or done % 10 == 0 or done == n_projects:
                                Logger.info(f"Orchestrator progress: {done}/{n_projects} projects")
                            proj = futures[future]
                            try:
                                future.result()
                            except Exception as exc:
                                record_error(
                                    proj["DRPID"],
                                    f"Orchestrator module={module!r} worker exception: {exc}",
                                )
            return
