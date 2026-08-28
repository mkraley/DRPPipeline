"""Quick check published view file extraction for one project."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.argv = [sys.argv[0], "upload"]
from utils.Args import Args  # noqa: E402
from utils.Logger import Logger  # noqa: E402

Args.initialize()
Logger.initialize(log_level="WARNING")

from upload.DataLumosAuthenticator import wait_for_human_verification  # noqa: E402
from upload.DataLumosBrowserSession import DataLumosBrowserSession  # noqa: E402
from verify.DatalumosViewFileStats import DatalumosViewFileStats, set_records_per_page  # noqa: E402


def main() -> None:
    """Print published-view filenames for DRPID 430."""
    row = sqlite3.connect("adc.db").execute(
        "SELECT DRPID, datalumos_id, published_url, title FROM projects WHERE DRPID = 430"
    ).fetchone()
    print("db row:", row)
    published_url = row[2]
    session = DataLumosBrowserSession()
    page = session.ensure_browser()
    session.ensure_authenticated()
    page.goto(published_url, wait_until="load", timeout=120000)
    wait_for_human_verification(page, timeout=60000)
    set_records_per_page(page, page_size=100)
    stats = DatalumosViewFileStats.from_page(page)
    print("error:", stats.error, "count:", stats.file_count)
    for name in stats.file_names:
        flag = " ***" if len(name) == 100 else ""
        print(f"  len={len(name):3d}{flag} | {name}")
    session.close()


if __name__ == "__main__":
    main()
