"""
Trial the DataLumos deposit API on one project without changing the uploader.

Creates a DataLumos project, writes metadata through the deposit API, and
does not update Storage. DRPIDs at or below 2500 are refused so current
upload batches are left alone.

Do not run this while ``python main.py upload --retry`` is logged into
DataLumos. A second browser on the same account can end that session.

From the repo root:

    python scripts/trial_datalumos_deposit.py --drpid 2501
    python scripts/trial_datalumos_deposit.py --drpid 2501 -c config.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

MIN_TRIAL_DRPID = 2500


def require_trial_drpid(drpid: int) -> None:
    """
    Refuse a DRPID that may belong to a current upload batch.

    Args:
        drpid: Storage id requested for the trial.

    Raises:
        ValueError: When ``drpid`` is not greater than 2500.
    """
    if drpid <= MIN_TRIAL_DRPID:
        raise ValueError(f"Trial DRPID must be greater than {MIN_TRIAL_DRPID} (got {drpid})")


def project_is_ready(project: dict[str, Any] | None, drpid: int) -> str:
    """
    Return an error message when the row cannot be used, else an empty string.

    The row is only read. Status and ``datalumos_id`` are not requirements.
    """
    if project is None:
        return f"Project with DRPID={drpid} was not found"
    if not str(project.get("title") or "").strip():
        return f"DRPID={drpid} is missing a title"
    if not str(project.get("summary") or "").strip():
        return f"DRPID={drpid} is missing a summary"
    return ""


def main(argv: list[str] | None = None) -> int:
    """Run the deposit-API trial for one DRPID."""
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
    parser = argparse.ArgumentParser(description="Trial DataLumos deposit API metadata writes.")
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
    return project, project_is_ready(project, drpid)


def _execute_trial(drpid: int, project: dict[str, Any]) -> int:
    """Create the DataLumos project and write metadata. Storage is not updated."""
    from upload.DataLumosBrowserSession import DataLumosBrowserSession
    from upload.DataLumosDepositClient import DataLumosDepositClient
    from upload.DepositMetadata import trial_metadata_from_project
    from upload.DepositMetadataWriter import DepositMetadataWriter
    from upload.deposit_field_match import match_fields

    metadata = trial_metadata_from_project(project)
    print(f"DRPID={drpid} status={project.get('status')!r} title={metadata.title!r}")
    print("Storage will not be updated.")
    log_path = REPO_ROOT / "debug" / f"deposit_trial_{drpid}.jsonl"
    session = DataLumosBrowserSession()
    path = ""
    try:
        page = session.ensure_browser()
        session.ensure_authenticated()
        client = DataLumosDepositClient(page, log_path=log_path)
        client.ensure_deposit_page()
        path = client.create_project(metadata.title)
        DepositMetadataWriter(client).fill_metadata(path, metadata)
        written = match_fields(client.get_attributes(path))
    except Exception as exc:
        print(f"DRPID={drpid}: FAIL — {exc}", file=sys.stderr)
        if path:
            print(f"Partial DataLumos project: {path}", file=sys.stderr)
        return 1
    finally:
        session.close()
    _print_result(drpid, path, log_path, written)
    return 0


def _print_result(drpid: int, path: str, log_path: Path, written: dict[str, Any]) -> None:
    """Print the created path and the attributes read back after the posts."""
    print(f"DRPID={drpid}: created {path}")
    print(f"Request log: {log_path}")
    for field, attr in sorted(written.items()):
        print(f"  {field}: label={attr.label!r} value={attr.value!r}")
    print(
        "Database was not modified. Delete the TRIAL project from the "
        "DataLumos workspace when finished."
    )


if __name__ == "__main__":
    raise SystemExit(main())
