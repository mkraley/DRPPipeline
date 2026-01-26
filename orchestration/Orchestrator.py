"""
Orchestrator for DRP Pipeline.

Central loop: list_eligible_projects and run/run_one only here. Resolves module
from MODULES, dispatches to _run_sourcing or _run_db_fed.
"""

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from storage import Storage
from utils.Args import Args
from utils.Logger import Logger


def _collectors_run_one_stub(project: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stub for collectors run_one. Raises NotImplementedError.

    Replaced by real implementation when SocrataCollector is wired to
    return ModuleResult (success, errors, warnings, updates).
    """
    raise NotImplementedError("collectors run_one not yet implemented")


def _noop_run(_num_rows: Optional[int]) -> None:
    """No-op module: does nothing, used for tests and entrypoints that don't need a real module."""
    pass


MODULES: Dict[str, Dict[str, Any]] = {
    "noop": {
        "prereq": None,
        "run": _noop_run,
    },
    "sourcing": {
        "prereq": None,
        "run": None,  # Set below after Sourcing is imported
    },
    "collectors": {
        "prereq": "sourcing",
        "run_one": _collectors_run_one_stub,
    },
}


def _get_sourcing_run() -> Callable[[Optional[int]], None]:
    """Return Sourcing().run bound with limit. Used to avoid import cycle."""
    from sourcing.Sourcing import Sourcing

    def _run(num_rows: Optional[int]) -> None:
        Sourcing().run(limit=num_rows)

    return _run


# Wire Sourcing into MODULES (done at import to avoid cycle at module top level)
MODULES["sourcing"]["run"] = _get_sourcing_run()


class Orchestrator:
    """
    Runs a single module (sourcing, collectors, etc.) on a batch of projects.

    For modules with no prereq (sourcing): calls run(storage, num_rows) once.
    For DB-fed modules: list_eligible_projects(prereq, num_rows), then
    run_one(project) for each, applying results (update_record / append_to_field).
    """

    @classmethod
    def run(cls, module: str) -> None:
        """
        Run the named module. Dispatches to _run_sourcing or _run_db_fed.

        Args:
            module: Module name (e.g. "sourcing", "collectors").

        Raises:
            ValueError: If module is not in MODULES.
        """
        if module not in MODULES:
            valid = ", ".join(sorted(MODULES.keys()))
            raise ValueError(f"Unknown module {module!r}. Valid: {valid}")
        info = MODULES[module]
        prereq = info["prereq"]
        num_rows: Optional[int] = getattr(Args, "num_rows", None)
        db_path: Optional[Path] = Path(Args.db_path) if getattr(Args, "db_path", None) else None
        impl = getattr(Args, "storage_implementation", None) or "StorageSQLLite"
        Storage.initialize(impl, db_path=db_path)
        Logger.info(f"Orchestrator running module={module!r} num_rows={num_rows}")
        if prereq is None:
            cls._run_sourcing(num_rows)
        else:
            cls._run_db_fed(module, num_rows)
        Logger.info(f"Orchestrator finished module={module!r}")

    @classmethod
    def _run_sourcing(cls, num_rows: Optional[int]) -> None:
        """Run the sourcing module: one call to run(num_rows)."""
        MODULES["sourcing"]["run"](num_rows)

    @classmethod
    def _run_db_fed(cls, module: str, num_rows: Optional[int]) -> None:
        """Run a DB-fed module: list_eligible_projects, then run_one per project, apply result."""
        info = MODULES[module]
        prereq = info["prereq"]
        run_one = info["run_one"]
        projects = Storage.list_eligible_projects(prereq, num_rows)
        Logger.info(f"Orchestrator module={module!r} eligible projects={len(projects)}")
        for proj in projects:
            drpid = proj["DRPID"]
            try:
                result = run_one(proj)
                if result.get("success"):
                    updates = result.get("updates", {})
                    updates["status"] = module
                    Storage.update_record(drpid, updates)
                    for w in result.get("warnings", []):
                        Storage.append_to_field(drpid, "warnings", w)
                else:
                    for e in result.get("errors", []):
                        Storage.append_to_field(drpid, "errors", e)
            except Exception as exc:
                Storage.append_to_field(drpid, "errors", str(exc))
                Logger.warning(f"Orchestrator module={module!r} DRPID={drpid} exception: {exc}")
                continue
