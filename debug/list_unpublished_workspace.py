"""
Read the DataLumos workspace sidebar without waiting for the page to finish.

The NPS workspace paints the left-hand project list, then stalls on a
subsidiary request. This script logs in, waits only until that list is in
the DOM, scrolls it, and writes projects that are not marked (Published).

Usage:
  python debug\\list_unpublished_workspace.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cleanup_inprogress.workspace_list import (  # noqa: E402
    is_published_entry,
    project_url,
    workspace_id_from_entry,
)
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError  # noqa: E402

from upload.DataLumosBrowserSession import DataLumosBrowserSession  # noqa: E402
from utils.Args import Args  # noqa: E402
from utils.Logger import Logger  # noqa: E402

WORKSPACE_URL = "https://www.datalumos.org/datalumos/workspace"
OUT_DIR = ROOT / "debug"
ALL_CSV = OUT_DIR / "workspace_sidebar.csv"
UNPUBLISHED_CSV = OUT_DIR / "unpublished_workspace_projects.csv"
PENDING_TXT = OUT_DIR / "workspace_pending_requests.txt"
_LIST_TIMEOUT_MS = 90000
_SCROLL_PAUSE_MS = 250
_MAX_SCROLLS = 80

_SNAPSHOT_JS = """
() => {
  const lists = [...document.querySelectorAll('ul.list-group')];
  const items = [];
  for (const ul of lists) {
    for (const li of ul.querySelectorAll(':scope > li')) {
      const link = li.querySelector('a');
      items.push({
        text: (li.innerText || '').trim(),
        href: link ? (link.getAttribute('href') || '') : '',
      });
    }
  }
  return items;
}
"""

_SCROLL_JS = """
() => {
  const ul = document.querySelector('ul.list-group');
  if (!ul) return {scrolled: false, atEnd: true};
  let node = ul.parentElement;
  while (node) {
    const style = getComputedStyle(node);
    const scrollable = /(auto|scroll)/.test(style.overflowY)
      && node.scrollHeight > node.clientHeight + 20;
    if (scrollable) {
      const before = node.scrollTop;
      node.scrollTop = Math.min(node.scrollTop + node.clientHeight, node.scrollHeight);
      const atEnd = node.scrollTop + node.clientHeight >= node.scrollHeight - 5;
      return {scrolled: node.scrollTop !== before, atEnd};
    }
    node = node.parentElement;
  }
  return {scrolled: false, atEnd: true};
}
"""


def _snapshot(page: Any) -> list[dict[str, str]]:
    """Return sidebar rows currently in the DOM."""
    rows = page.evaluate(_SNAPSHOT_JS)
    return [row for row in rows if (row.get("text") or row.get("href"))]


def _collect_sidebar(page: Any) -> list[dict[str, str]]:
    """
    Scroll the sidebar and keep every distinct row seen.

    Args:
        page: Playwright page with the workspace list in the DOM.

    Returns:
        Sidebar rows keyed by project id, or by label when no id is present.
    """
    found: dict[str, dict[str, str]] = {}
    idle_rounds = 0
    page.set_default_timeout(8000)
    for _ in range(_MAX_SCROLLS):
        before = len(found)
        try:
            batch = _snapshot(page)
            state = page.evaluate(_SCROLL_JS)
        except PlaywrightTimeoutError:
            Logger.warning("Sidebar scroll timed out; keeping rows already read")
            break
        for row in batch:
            text = row.get("text") or ""
            href = row.get("href") or ""
            key = workspace_id_from_entry(text, href) or text
            if key:
                found[key] = {"text": text, "href": href}
        if len(found) == before and state.get("atEnd"):
            idle_rounds += 1
        else:
            idle_rounds = 0
        if idle_rounds >= 2:
            break
        page.wait_for_timeout(_SCROLL_PAUSE_MS)
    return list(found.values())


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    """Write sidebar rows as UTF-8 with BOM."""
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["workspace_id", "published", "text", "url"]
        )
        writer.writeheader()
        for row in rows:
            workspace_id = workspace_id_from_entry(row["text"], row["href"]) or ""
            writer.writerow(
                {
                    "workspace_id": workspace_id,
                    "published": "yes" if is_published_entry(row["text"]) else "no",
                    "text": row["text"].replace("\n", " | "),
                    "url": project_url(workspace_id) if workspace_id else "",
                }
            )


def _track_requests(page: Any) -> dict[str, str]:
    """Record in-flight request URLs so a hung subsidiary call can be identified."""
    pending: dict[str, str] = {}

    def _start(request: Any) -> None:
        pending[request.url] = request.resource_type

    def _done(request: Any) -> None:
        pending.pop(request.url, None)

    page.on("request", _start)
    page.on("requestfinished", _done)
    page.on("requestfailed", _done)
    return pending


def main() -> None:
    """Log in, read the sidebar, and write unpublished project ids."""
    sys.argv = ["list_unpublished_workspace", "noop"]
    Args._initialized = False
    Args.initialize()
    Logger.initialize(log_level="INFO")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    session = DataLumosBrowserSession()
    pending: dict[str, str] = {}
    try:
        page = session.ensure_browser()
        pending = _track_requests(page)
        session.ensure_authenticated()
        Logger.info("Opening workspace without waiting for full load")
        page.goto(WORKSPACE_URL, wait_until="commit", timeout=_LIST_TIMEOUT_MS)
        page.locator("ul.list-group").first.wait_for(
            state="visible", timeout=_LIST_TIMEOUT_MS
        )
        rows = _collect_sidebar(page)
        _write_csv(ALL_CSV, rows)
        unpublished = [row for row in rows if not is_published_entry(row["text"])]
        _write_csv(UNPUBLISHED_CSV, unpublished)
        Logger.info(
            "Sidebar rows=%s unpublished=%s",
            len(rows),
            len(unpublished),
        )
    finally:
        PENDING_TXT.write_text(
            "\n".join(f"{kind}\t{url}" for url, kind in pending.items()),
            encoding="utf-8-sig",
        )
        session.close()


if __name__ == "__main__":
    main()
