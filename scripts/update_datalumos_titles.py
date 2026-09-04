"""
Update DataLumos project titles for uploaded DRPIDs.

Opens each project's DataLumos workspace page, applies colon→dash title rules
and the DataLumos length limit, then Save & Apply when the field differs.

Eligible statuses: ``uploaded``, ``uploaded - large file``.

From repo root:

    python scripts/update_datalumos_titles.py --ids 11-20
    python scripts/update_datalumos_titles.py --ids 12,15,17 --dry-run
    python scripts/update_datalumos_titles.py --ids 11-30 -c config.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

ELIGIBLE_STATUSES = frozenset({"uploaded", "uploaded - large file"})
WORKSPACE_URL = "https://www.datalumos.org/datalumos/workspace"


def project_url(workspace_id: str) -> str:
    """Build the DataLumos project workspace URL."""
    return f"{WORKSPACE_URL}?goToLevel=project&goToPath=/datalumos/{workspace_id}#"


def select_eligible_projects(
    storage: Any,
    ids: list[int],
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Load projects for ``ids`` that are eligible for a DataLumos title update.

    Args:
        storage: Initialized Storage facade.
        ids: DRPIDs to consider.

    Returns:
        ``(projects, skip_messages)``.
    """
    projects: list[dict[str, Any]] = []
    skips: list[str] = []
    for drpid in ids:
        project = storage.get(drpid)
        if project is None:
            skips.append(f"DRPID={drpid}: SKIP — not in storage")
            continue
        status = (project.get("status") or "").strip()
        if status not in ELIGIBLE_STATUSES:
            skips.append(
                f"DRPID={drpid}: SKIP — status={status!r} "
                f"(need {' or '.join(sorted(ELIGIBLE_STATUSES))})"
            )
            continue
        workspace_id = (project.get("datalumos_id") or "").strip()
        if not workspace_id:
            skips.append(f"DRPID={drpid}: SKIP — missing datalumos_id")
            continue
        title = (project.get("title") or "").strip()
        if not title:
            skips.append(f"DRPID={drpid}: SKIP — empty title")
            continue
        projects.append(project)
    return projects, skips


def update_one_project_title(
    page: Any,
    project: dict[str, Any],
    *,
    timeout: int,
) -> tuple[str, bool]:
    """
    Navigate to the project page and update the title field if needed.

    Args:
        page: Authenticated Playwright page.
        project: Storage project record.
        timeout: Playwright timeout in ms.

    Returns:
        ``(written_title, changed)``.
    """
    from upload.DataLumosAuthenticator import wait_for_human_verification
    from upload.DataLumosFormFiller import DataLumosFormFiller
    from utils.Logger import Logger
    from utils.title_utils import prepare_datalumos_title

    drpid = int(project["DRPID"])
    workspace_id = str(project["datalumos_id"]).strip()
    title = str(project.get("title") or "")
    desired = prepare_datalumos_title(title)

    url = project_url(workspace_id)
    Logger.info("Opening DataLumos project %s for DRPID=%s", workspace_id, drpid)
    page.goto(url, wait_until="domcontentloaded")
    # Prefer a concrete UI marker over networkidle (can hang on workspace pages).
    page.locator("span", has_text="Edit Project Header").first.wait_for(
        state="visible", timeout=120000
    )
    wait_for_human_verification(page, timeout=60000)

    form_filler = DataLumosFormFiller(page, timeout=timeout)
    written, changed = form_filler.update_project_title(title)
    if written != desired:
        raise RuntimeError(
            f"DRPID={drpid}: unexpected written title {written!r} != {desired!r}"
        )
    return written, changed


def main() -> int:
    """CLI entry: update DataLumos titles for ``--ids``."""
    parser = argparse.ArgumentParser(
        description=(
            "Update DataLumos titles for uploaded / uploaded - large file projects."
        )
    )
    parser.add_argument(
        "--ids",
        required=True,
        help="Comma-separated DRPIDs and ranges (e.g. 11-20,25)",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=REPO_ROOT / "config.json",
        help="Config JSON (default: ./config.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned title updates without opening a browser",
    )
    args = parser.parse_args()

    if not args.config.is_file():
        print(f"ERROR: config not found: {args.config}", file=sys.stderr)
        return 1

    from storage import Storage
    from upload.DataLumosBrowserSession import DataLumosBrowserSession
    from utils.Args import Args
    from utils.Logger import Logger
    from utils.drpid_list import parse_drpid_ids
    from utils.title_utils import prepare_datalumos_title

    try:
        ids = parse_drpid_ids(args.ids)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    Args.initialize_from_config(args.config)
    Logger.initialize(
        log_level=Args.log_level,
        log_color=getattr(Args, "log_color", False),
    )
    Storage.initialize(Args.storage_implementation, db_path=Path(Args.db_path))

    if not Args.datalumos_username or not Args.datalumos_password:
        print(
            "ERROR: datalumos_username and datalumos_password must be set in config.",
            file=sys.stderr,
        )
        return 1

    projects, skips = select_eligible_projects(Storage, ids)
    for msg in skips:
        print(msg)

    if not projects:
        print("No eligible projects to update.")
        return 1 if skips else 0

    if args.dry_run:
        for project in projects:
            drpid = int(project["DRPID"])
            desired = prepare_datalumos_title(str(project.get("title") or ""))
            print(
                f"DRPID={drpid}: WOULD SET title={desired!r} "
                f"(datalumos_id={project.get('datalumos_id')})"
            )
        print(f"Dry-run complete: {len(projects)} project(s).")
        return 0

    session = DataLumosBrowserSession()
    exit_code = 0
    updated = 0
    unchanged = 0
    try:
        page = session.ensure_browser()
        session.ensure_authenticated()
        for project in projects:
            drpid = int(project["DRPID"])
            try:
                written, changed = update_one_project_title(
                    page,
                    project,
                    timeout=int(Args.upload_timeout),
                )
                if changed:
                    updated += 1
                    print(f"DRPID={drpid}: OK — updated title to {written!r}")
                else:
                    unchanged += 1
                    print(f"DRPID={drpid}: OK — already matched {written!r}")
            except Exception as exc:
                exit_code = 1
                print(f"DRPID={drpid}: FAIL — {exc}")
    finally:
        session.close()

    print(
        f"Done: updated={updated} unchanged={unchanged} "
        f"errors={'yes' if exit_code else 'no'} eligible={len(projects)}"
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
