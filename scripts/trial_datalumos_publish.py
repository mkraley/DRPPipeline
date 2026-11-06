"""
Time one DataLumos publish made with the deposit HTTP API.

Publishes one already-uploaded project (DRPID > 2500), writes a redacted
request log, and prints how long login, storage, publish, and the view check
took. Storage is updated only after the public view URL responds.

Do not run this while ``python main.py upload --retry`` is logged into
DataLumos. A second browser on the same account can end that session.

From the repo root:

    python scripts/trial_datalumos_publish.py --drpid 2501
    python scripts/trial_datalumos_publish.py --drpid 2501 -c config.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.trial_datalumos_deposit import require_trial_drpid
from scripts.trial_elapsed import finish_timing, format_trial_elapsed, lap, new_clock, total_ms


def project_can_publish(project: dict[str, Any] | None, drpid: int) -> str:
    """
    Return an error message when the row cannot be published, else empty.

    Args:
        project: Storage row, or None when the id is missing.
        drpid: Storage id requested for the trial.
    """
    if project is None:
        return f"Project with DRPID={drpid} was not found"
    status = str(project.get("status") or "")
    if status != "uploaded":
        return f"DRPID={drpid} status is {status!r}, expected 'uploaded'"
    if not str(project.get("datalumos_id") or "").strip():
        return f"DRPID={drpid} has no datalumos_id"
    return ""


def record_published(drpid: int, view_url: str, public: bool) -> bool:
    """
    Mark the project published only when the view URL is public.

    Args:
        drpid: Storage id.
        view_url: Public DataLumos view URL.
        public: True when that URL responded without a login page.

    Returns:
        True when Storage was updated.
    """
    if not public:
        return False
    from storage import Storage

    Storage.update_record(drpid, {"published_url": view_url, "status": "published"})
    return True


def main(argv: list[str] | None = None) -> int:
    """Publish one project over HTTP and print the elapsed time."""
    args = _parse_args(argv)
    try:
        require_trial_drpid(args.drpid)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if not args.config.is_file():
        print(f"ERROR: config not found: {args.config}", file=sys.stderr)
        return 1
    project, error = _load_project(args.config, args.drpid)
    if error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    assert project is not None
    return _execute_trial(args.drpid, project)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse the trial CLI."""
    parser = argparse.ArgumentParser(description="Time one DataLumos HTTP publish.")
    parser.add_argument("--drpid", type=int, required=True, help="Storage DRPID greater than 2500")
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Path("config.json"),
        help="Pipeline config file",
    )
    return parser.parse_args(argv)


def _load_project(config: Path, drpid: int) -> tuple[dict[str, Any] | None, str]:
    """Initialize Storage and return the row, or an error message."""
    from storage import Storage
    from utils.Args import Args
    from utils.Logger import Logger

    Args.initialize_from_config(config)
    Logger.initialize(log_level=Args.log_level, log_color=getattr(Args, "log_color", False))
    Storage.initialize(Args.storage_implementation, db_path=Path(Args.db_path))
    if not Args.datalumos_username or not Args.datalumos_password:
        return None, "datalumos_username and datalumos_password must be set in config."
    project = Storage.get(drpid)
    return project, project_can_publish(project, drpid)


def _execute_trial(drpid: int, project: dict[str, Any]) -> int:
    """Log in, check inventory, publish, and confirm the public view URL."""
    from upload.DataLumosBrowserSession import DataLumosBrowserSession

    workspace_id = str(project.get("datalumos_id") or "").strip()
    print(f"DRPID={drpid} datalumos_id={workspace_id} files={project.get('num_files')}")
    print("Storage is updated only after the public view URL responds.")
    log_path = REPO_ROOT / "debug" / f"publish_trial_{drpid}.jsonl"
    clock = new_clock()
    phases: dict[str, int] = {}
    session = DataLumosBrowserSession()
    try:
        view_url, public = _publish_one(session, project, log_path, clock, phases)
        print(format_trial_elapsed(total_ms(clock), phases))
        print(view_url)
        if not record_published(drpid, view_url, public):
            print(f"Published view URL was not available: {view_url}", file=sys.stderr)
            finish_timing(log_path, clock, phases)
            return 1
        finish_timing(log_path, clock, phases)
        print(f"DRPID={drpid} marked published")
        return 0
    except Exception as exc:
        print(f"DRPID={drpid}: FAIL — {exc}", file=sys.stderr)
        finish_timing(log_path, clock, phases)
        return 1
    finally:
        session.close()


def _publish_one(
    session: Any,
    project: dict[str, Any],
    log_path: Path,
    clock: dict[str, float],
    phases: dict[str, int],
) -> tuple[str, bool]:
    """Return the view URL and whether it was public."""
    from publisher.DataLumosPublishClient import DataLumosPublishClient
    from publisher.DataLumosPublisher import VIEW_URL_TEMPLATE
    from publisher.WorkspaceFileStats import mismatches_for_storage_status

    page = session.ensure_browser()
    session.ensure_authenticated()
    lap(clock, phases, "login")
    client = DataLumosPublishClient(page, log_path=log_path)
    workspace_id = str(project.get("datalumos_id") or "").strip()
    status = client.storage_status(workspace_id)
    mismatches = mismatches_for_storage_status(status, project)
    lap(clock, phases, "viewStorage")
    if mismatches:
        raise RuntimeError("Inventory does not match: " + "; ".join(mismatches))
    client.publish_project(workspace_id)
    lap(clock, phases, "publish")
    view_url = VIEW_URL_TEMPLATE.format(workspace_id=workspace_id, version="V1")
    public = client.view_is_public(view_url)
    lap(clock, phases, "view")
    return view_url, public


if __name__ == "__main__":
    raise SystemExit(main())
