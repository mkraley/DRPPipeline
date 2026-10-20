"""Dump controls on one DataLumos project page. Usage: python debug\\dump_delete_controls.py <id>"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cleanup_inprogress.workspace_list import project_url
from upload.DataLumosBrowserSession import DataLumosBrowserSession
from utils.Args import Args
from utils.Logger import Logger

OUT = ROOT / "debug"


def main() -> int:
    """Open one project and write its buttons plus a screenshot."""
    workspace_id = sys.argv[1].strip()
    sys.argv = ["dump_delete_controls", "noop"]
    Args._initialized = False
    Args.initialize()
    Logger.initialize(log_level="INFO")
    session = DataLumosBrowserSession()
    try:
        page = session.ensure_browser()
        session.ensure_authenticated()
        page.goto(project_url(workspace_id), wait_until="commit", timeout=45000)
        cdp = page.context.new_cdp_session(page)
        expression = """(() => {
          const buttons = [...document.querySelectorAll('button')]
            .map(b => (b.innerText || '').trim()).filter(Boolean).slice(0, 40);
          const h1 = document.querySelector('h1');
          return JSON.stringify({
            href: location.href,
            ready: document.readyState,
            h1: h1 ? h1.innerText.trim().slice(0, 120) : '',
            buttons
          });
        })()"""
        for _ in range(12):
            result = cdp.send(
                "Runtime.evaluate",
                {"expression": expression, "returnByValue": True},
            )
            print(result.get("result", {}).get("value"))
            page.wait_for_timeout(2000)
        cdp.send("Runtime.evaluate", {"expression": "window.stop()"})
        print(f"url={page.url}")
        text = page.locator("body").inner_text(timeout=15000)
        (OUT / "delete_page_text.txt").write_text(text, encoding="utf-8-sig")
        buttons = page.locator("button, a").evaluate_all(
            """els => els.slice(0, 80).map(el => ({
                tag: el.tagName,
                text: (el.innerText || '').trim().slice(0, 80),
                cls: String(el.className || '').slice(0, 120)
            }))"""
        )
        lines = [f"{item['tag']} | {item['text']} | {item['cls']}" for item in buttons]
        (OUT / "delete_page_controls.txt").write_text("\n".join(lines), encoding="utf-8-sig")
        page.screenshot(path=str(OUT / "delete_page.png"), full_page=False)
        print(f"url={page.url}")
        print(f"controls={len(lines)}")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
