"""
Orchestrator for DRP Pipeline.

Central loop: list_eligible_projects and run() only here. Resolves module
from MODULES registry, dynamically imports module classes by name, and calls run(drpid).
"""

import importlib
import pkgutil
import sys
from pathlib import Path
from typing import Any, Dict, Optional

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
    "collectors": {
        "prereq": "sourcing",
        "class_name": "SocrataCollector",  # Will implement ModuleProtocol directly
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
        
        # Clear database if requested
        if Args.delete_all_db_entries:
            Logger.warning("Deleting all database entries as requested by --delete-all-db-entries flag")
            Storage.clear_all_records()
        
        num_rows: Optional[int] = Args.num_rows
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
                source_url = proj.get("source_url", "")
                Logger.set_current_drpid(drpid)
                try:
                    Logger.info(f"Starting project with source URL {source_url}")
                    module_instance.run(drpid)
                except Exception as exc:
                    record_error(
                        drpid,
                        f"Orchestrator module={module!r} DRPID={drpid} exception: {exc}",
                    )
                    continue
                finally:
                    Logger.clear_current_drpid()
        
        Logger.info(f"Orchestrator finished module={module!r}")
