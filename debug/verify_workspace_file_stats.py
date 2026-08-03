"""Verify workspace file stats after recordsPerPage fix."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.argv = [sys.argv[0], "publisher"]

from upload.DataLumosAuthenticator import wait_for_human_verification
from upload.DataLumosBrowserSession import DataLumosBrowserSession
from publisher.WorkspaceFileStats import workspace_file_stats_from_page
from utils.Args import Args
from utils.Logger import Logger

Args.initialize()
Logger.initialize(log_level="WARNING", log_file=False)

workspace_id = "251395"
url = (
    "https://www.datalumos.org/datalumos/workspace"
    f"?goToLevel=project&goToPath=/datalumos/{workspace_id}#"
)
session = DataLumosBrowserSession()
page = session.ensure_browser()
session.ensure_authenticated()
page.goto(url, wait_until="domcontentloaded", timeout=120000)
page.wait_for_load_state("networkidle", timeout=120000)
wait_for_human_verification(page, timeout=60000)

stats = workspace_file_stats_from_page(page)
print(f"file_count={stats.file_count} error={stats.error}")
session.close()
assert stats.error is None
assert stats.file_count == 48
