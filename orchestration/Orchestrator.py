"""
Orchestrator for DRP Pipeline.

Central loop: list_eligible_projects and run() only here. Resolves module
from MODULES registry, dynamically imports module classes by name, and calls run(drpid).
"""

from pathlib import Path
from typing import Any, Dict, Optional

from storage import Storage
from utils.Args import Args
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
    "collectors": {
        "prereq": "sourcing",
        "class_name": "SocrataCollector",  # Will implement ModuleProtocol directly
    },
}


def _find_module_class(class_name: str) -> type:
    """
    Dynamically find and import a module class by name.
    
    Searches common module locations: sourcing, collectors, etc.
    
    Args:
        class_name: Name of the class (e.g., "Sourcing", "SocrataCollector")
        
    Returns:
        The module class
        
    Raises:
        ImportError: If the class cannot be found or imported
    """
    # Common module locations to search
    search_paths = [
        f"sourcing.{class_name}",
        f"collectors.{class_name}",
        f"orchestration.{class_name}",
    ]
    
    for module_path in search_paths:
        try:
            module = __import__(module_path, fromlist=[class_name])
            if hasattr(module, class_name):
                return getattr(module, class_name)
        except ImportError:
            continue
    
    raise ImportError(
        f"Could not find module class '{class_name}'. "
        f"Searched: {', '.join(search_paths)}"
    )


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
        impl = getattr(Args, "storage_implementation", None) or "StorageSQLLite"
        Storage.initialize(impl, db_path=Path(Args.db_path))
        
        num_rows: Optional[int] = getattr(Args, "num_rows", None)
        Logger.info(f"Orchestrator running module={module!r} num_rows={num_rows}")
        
        # Handle noop directly
        if module == "noop":
            Logger.info(f"Orchestrator finished module={module!r}")
            return
        
        # Load and instantiate module class
        module_class = _find_module_class(class_name)
        module_instance = module_class()
        
        if prereq is None:
            # Modules with no prereq: call run(-1) once
            module_instance.run(-1)
        else:
            # Modules with prereq: call run(drpid) for each eligible project
            projects = Storage.list_eligible_projects(prereq, num_rows)
            Logger.info(f"Orchestrator module={module!r} eligible projects={len(projects)}")
            
            for proj in projects:
                drpid = proj["DRPID"]
                try:
                    module_instance.run(drpid)
                except Exception as exc:
                    Storage.append_to_field(drpid, "errors", str(exc))
                    Logger.warning(f"Orchestrator module={module!r} DRPID={drpid} exception: {exc}")
                    continue
        
        Logger.info(f"Orchestrator finished module={module!r}")
