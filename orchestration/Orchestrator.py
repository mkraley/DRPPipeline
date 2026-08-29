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
from utils.Errors import derive_error_status, is_error_status, record_crash, record_error
from utils.Logger import Logger


# Batch modules that collect data from source URLs (not upload/publish/verify).
_COLLECTOR_MODULES = frozenset({
    "adc_collector",
    "adc_globus_collector",
    "adc_globus_survey",
    "socrata_collector",
    "catalog_collector",
    "cms_collector",
    "usfs_collector",
})


def _maybe_claim_inventory_sheet(drpid: int, module: str) -> None:
    """
    After a successful collector run, set Claimed on the inventory sheet row.

    Args:
        drpid: Project DRPID.
        module: Orchestrator module name.
    """
    if module not in _COLLECTOR_MODULES:
        return
    record = Storage.get(drpid)
    if not record:
        return
    from utils.sheet_claimed_update import (
        claim_project_on_inventory_sheet,
        should_claim_after_collector_status,
    )

    if not should_claim_after_collector_status(record.get("status")):
        return
    claim_project_on_inventory_sheet(drpid, record)


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
    "adc_collector": {
        "prereq": "sourced",
        "class_name": "AdcCollector",
    },
    "adc_globus_collector": {
        "prereq": "collected - external archive",
        "class_name": "AdcGlobusCollector",
    },
    "adc_globus_survey": {
        "prereq": "collected - external archive",
        "class_name": "AdcGlobusSurvey",
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
    "upload_large_files": {
        "prereq": "uploaded - large file",
        "class_name": "UploadLargeFiles",
    },
    "publisher": {
        "prereq": "uploaded",
        "class_name": "DataLumosPublisher",
    },
    "republisher": {
        "prereq": "re-uploaded",
        "class_name": "DataLumosRepublisher",
    },
    "verify_upload": {
        "prereq": "updated_inventory",
        "class_name": "UploadVerifier",
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


def list_pipeline_modules(*, include_noop: bool = False) -> list[str]:
    """
    Return module names for CLI and UI lists.

    Excludes ``noop`` unless requested and omits legacy ``*_sourcing`` aliases
    (use ``sourcing`` with ``Args.source`` instead).

    Args:
        include_noop: When True, include the ``noop`` module.

    Returns:
        Ordered module names from :data:`MODULES`.
    """
    names: list[str] = []
    for name in MODULES:
        if name == "noop" and not include_noop:
            continue
        if name.endswith("_sourcing"):
            continue
        names.append(name)
    return names


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


def _merge_project_lists(
    project_lists: list[list[Dict[str, Any]]],
    num_rows: Optional[int],
) -> list[Dict[str, Any]]:
    """
    Merge project lists, dedupe by DRPID, sort by DRPID, and apply a row limit.

    Args:
        project_lists: Lists of project row dicts to combine.
        num_rows: Max projects to return. None = no limit.

    Returns:
        Deduplicated projects ordered by DRPID ASC, truncated to num_rows.
    """
    seen: set[int] = set()
    projects: list[Dict[str, Any]] = []
    for project_list in project_lists:
        for proj in project_list:
            drpid = proj["DRPID"]
            if drpid not in seen:
                seen.add(drpid)
                projects.append(proj)
    projects.sort(key=lambda p: p["DRPID"])
    if num_rows is not None:
        projects = projects[:num_rows]
    return projects


def _list_by_base_status(
    base_status: str,
    *,
    num_rows: Optional[int],
    start_row: Optional[int],
    start_drpid: Optional[int],
    retry: bool,
) -> list[Dict[str, Any]]:
    """
    List projects for a module prerequisite status.

    When ``retry`` is True, selects ``derive_error_status(base_status)`` and
    includes rows with a non-empty errors field. Each returned dict is tagged
    with ``_retry_base_status`` so the orchestrator can restore the base status
    before running the module.
    """
    lookup = derive_error_status(base_status) if retry else base_status
    if retry:
        projects = Storage.list_eligible_projects(
            lookup,
            num_rows,
            start_row,
            start_drpid,
            include_errored=True,
        )
        for proj in projects:
            proj["_retry_base_status"] = base_status
        return projects
    return Storage.list_eligible_projects(
        lookup, num_rows, start_row, start_drpid
    )


def _filter_by_ids(
    projects: list[Dict[str, Any]],
    ids: Optional[list[int]],
) -> list[Dict[str, Any]]:
    """Keep only projects whose DRPID is in ``ids`` (no-op when ids is None)."""
    if not ids:
        return projects
    id_set = set(ids)
    return [proj for proj in projects if proj["DRPID"] in id_set]


def _prepare_retry_project(proj: Dict[str, Any]) -> None:
    """
    Restore base status before a --retry run so modules can advance status.

    Leaves the errors field intact until success (see ``_finalize_retry_project``).
    """
    base = proj.get("_retry_base_status")
    if not base:
        return
    drpid = proj["DRPID"]
    Storage.update_record(drpid, {"status": base})
    Logger.info(
        f"Orchestrator retry: DRPID={drpid} status reset {proj.get('status')!r} -> {base!r}"
    )


def _finalize_retry_project(drpid: int) -> None:
    """Clear the errors field after a successful --retry run."""
    if not bool(getattr(Args, "retry", False)):
        return
    record = Storage.get(drpid)
    if record is None:
        return
    if is_error_status(record.get("status")):
        return
    Storage.update_record(drpid, {"errors": None})
    Logger.info(f"Orchestrator retry: DRPID={drpid} succeeded; errors cleared")


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
        retry: bool = bool(getattr(Args, "retry", False))
        ids: Optional[list[int]] = getattr(Args, "ids", None)
        Logger.info(
            f"Orchestrator running module={module!r} num_rows={num_rows} "
            f"start_row={start_row} start_drpid={start_drpid} "
            f"retry={retry} ids={ids!r}"
        )
        
        # Handle noop directly
        if module == "noop":
            Logger.info(f"Orchestrator finished module={module!r}")
            return

        # Handle interactive_collector: set DB path and start Flask app (app loads first eligible from Storage)
        if module == "interactive_collector":
            from interactive_collector.api_projects import get_interactive_prereq
            from interactive_collector.app import app as interactive_app

            prereq_status = get_interactive_prereq()
            Logger.info(
                "Starting interactive collector (open http://127.0.0.1:5000/) "
                "eligible_prereq=%r",
                prereq_status,
            )
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
            list_kwargs = {
                "num_rows": None if ids else num_rows,
                "start_row": None if ids else start_row,
                "start_drpid": None if ids else start_drpid,
                "retry": retry,
            }
            if module == "publisher":
                # Publisher also processes sheet-only statuses (no browser)
                from publisher.sheet_only_status import COLLECTOR_HOLD_PREFIXES

                hold_lists = [
                    Storage.list_eligible_projects_with_status_prefix(
                        prefix,
                        list_kwargs["num_rows"],
                        list_kwargs["start_row"],
                        list_kwargs["start_drpid"],
                        include_errored=retry,
                    )
                    for prefix in COLLECTOR_HOLD_PREFIXES
                ]
                projects = _merge_project_lists(
                    [
                        _list_by_base_status("uploaded", **list_kwargs),
                        _list_by_base_status("not_found", **list_kwargs),
                        _list_by_base_status("no_links", **list_kwargs),
                        _list_by_base_status("no dataset", **list_kwargs),
                        _list_by_base_status("gigantic upload", **list_kwargs),
                        _list_by_base_status("needs scripting", **list_kwargs),
                        *hold_lists,
                    ],
                    None if ids else num_rows,
                )
            elif module == "upload":
                projects = _merge_project_lists(
                    [
                        _list_by_base_status("collected", **list_kwargs),
                        _list_by_base_status("collected - large file", **list_kwargs),
                    ],
                    None if ids else num_rows,
                )
            elif module == "upload_large_files":
                from upload.UploadLargeFiles import is_eligible_for_upload_large_files

                # Always list without a row limit; apply num_rows after size filter.
                large_kwargs = {**list_kwargs, "num_rows": None}
                merged = _merge_project_lists(
                    [
                        _list_by_base_status("uploaded - large file", **large_kwargs),
                        _list_by_base_status("uploaded - expanded", **large_kwargs),
                    ],
                    None,
                )
                projects = [
                    proj for proj in merged
                    if is_eligible_for_upload_large_files(
                        {
                            **proj,
                            "status": proj.get("_retry_base_status")
                            or proj.get("status"),
                        }
                    )
                ]
                if not ids and num_rows is not None:
                    projects = projects[:num_rows]
            elif module == "verify_upload":
                if retry:
                    projects = _list_by_base_status(
                        "updated_inventory", **list_kwargs
                    )
                else:
                    # Normal mode also retries previously failed verifications
                    projects = _merge_project_lists(
                        [
                            _list_by_base_status(
                                "updated_inventory",
                                num_rows=list_kwargs["num_rows"],
                                start_row=list_kwargs["start_row"],
                                start_drpid=list_kwargs["start_drpid"],
                                retry=False,
                            ),
                            Storage.list_eligible_projects(
                                "updated_inventory-error",
                                list_kwargs["num_rows"],
                                list_kwargs["start_row"],
                                list_kwargs["start_drpid"],
                                include_errored=True,
                            ),
                        ],
                        None if ids else num_rows,
                    )
            elif module == "adc_globus_collector":
                from collectors.AdcGlobusCollector import is_globus_external_archive

                # List without row limit; filter Globus then apply num_rows.
                globus_kwargs = {**list_kwargs, "num_rows": None}
                candidates = _list_by_base_status(
                    "collected - external archive", **globus_kwargs
                )
                projects = [
                    proj for proj in candidates if is_globus_external_archive(proj)
                ]
                projects.sort(key=lambda p: p["DRPID"])
                if not ids and num_rows is not None:
                    projects = projects[:num_rows]
            elif module == "adc_globus_survey":
                from collectors.AdcGlobusSurvey import is_globus_external_archive

                globus_kwargs = {**list_kwargs, "num_rows": None}
                candidates = _list_by_base_status(
                    "collected - external archive", **globus_kwargs
                )
                projects = [
                    proj for proj in candidates if is_globus_external_archive(proj)
                ]
                projects.sort(key=lambda p: p["DRPID"])
                if not ids and num_rows is not None:
                    projects = projects[:num_rows]
            else:
                Logger.info(
                    f"Orchestrator listing eligible projects prereq={prereq!r} retry={retry}"
                )
                projects = _list_by_base_status(prereq, **list_kwargs)

            projects = _filter_by_ids(projects, ids)
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
                        if retry:
                            _prepare_retry_project(proj)
                        instance.run(drpid)
                        if retry:
                            _finalize_retry_project(drpid)
                        _maybe_claim_inventory_sheet(drpid, module)
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
                            if retry:
                                _prepare_retry_project(proj)
                            module_instance.run(drpid)
                            if retry:
                                _finalize_retry_project(drpid)
                            _maybe_claim_inventory_sheet(drpid, module)
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
