"""Source the seven Electric Quarterly Report CSV projects into ferc.db.

Run from the repo root after ``source`` in config.json is ``ferc``::

    python scripts/source_eqr_projects.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import collectors  # noqa: E402, F401
from sourcing.EqrProjects import insert_missing_eqr_projects  # noqa: E402
from storage import Storage  # noqa: E402
from utils.Args import Args  # noqa: E402
from utils.Logger import Logger  # noqa: E402


def main() -> int:
    """Insert any missing EQR year-range projects and print their DRPIDs."""
    _initialize()
    Storage.initialize(Args.storage_implementation, db_path=Path(Args.db_path))
    inserted = insert_missing_eqr_projects()
    if inserted:
        Logger.info("Inserted EQR projects: %s", ", ".join(str(drpid) for drpid in inserted))
    else:
        Logger.info("EQR projects are already sourced")
    print("inserted", " ".join(str(drpid) for drpid in inserted) or "none")
    return 0


def _initialize() -> None:
    """Load the active source config without treating this file's argv as a module."""
    sys.argv = ["source_eqr_projects", "source"]
    Args._initialized = False
    Args.initialize()
    Logger.initialize(log_level="INFO")


if __name__ == "__main__":
    raise SystemExit(main())
