"""Dump DataLumos filename lengths for one project."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.argv = [sys.argv[0], "upload"]
from utils.Args import Args  # noqa: E402
from utils.Logger import Logger  # noqa: E402

Args.initialize()
Logger.initialize(log_level="WARNING")

from publisher.WorkspaceFileStats import workspace_file_stats_from_page  # noqa: E402
from upload.DataLumosAuthenticator import wait_for_human_verification  # noqa: E402
from upload.DataLumosBrowserSession import DataLumosBrowserSession  # noqa: E402
from verify.DatalumosViewFileStats import DatalumosViewFileStats  # noqa: E402

WORKSPACE_ID = "250591"


def main() -> None:
    """Print workspace and published filenames with lengths."""
    session = DataLumosBrowserSession()
    page = session.ensure_browser()
    session.ensure_authenticated()

    ws_url = (
        "https://www.datalumos.org/datalumos/workspace"
        f"?goToLevel=project&goToPath=/datalumos/{WORKSPACE_ID}#"
    )
    page.goto(ws_url, wait_until="load", timeout=120000)
    wait_for_human_verification(page, timeout=60000)
    try:
        print("workspace h1:", page.locator("h1").first.inner_text(timeout=5000))
    except Exception as exc:
        print("workspace h1: (missing)", exc)
    ws = workspace_file_stats_from_page(page)
    print("workspace error:", ws.error)
    for name in ws.file_names:
        print(f"  ws len={len(name):3d} | {name}")

    pub_url = f"https://www.datalumos.org/datalumos/{WORKSPACE_ID}"
    page.goto(pub_url, wait_until="load", timeout=120000)
    wait_for_human_verification(page, timeout=60000)
    pub = DatalumosViewFileStats.from_page(page)
    print("published error:", pub.error)
    for name in pub.file_names:
        print(f"  pub len={len(name):3d} | {name}")

    session.close()


if __name__ == "__main__":
    main()
