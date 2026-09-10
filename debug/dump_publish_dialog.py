"""
Dump DataLumos publish-dialog controls for selector debugging.

Usage:
  python debug\\dump_publish_dialog.py <datalumos_id>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Project root on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage import Storage
from upload.DataLumosBrowserSession import DataLumosBrowserSession
from utils.Args import Args
from utils.Logger import Logger

OUT_DIR = ROOT / "debug"


def _dump_controls_js() -> str:
    """Return page.evaluate script that lists interactive controls."""
    return """
() => {
  const els = [...document.querySelectorAll(
    'input, button, select, textarea, label, [role="dialog"], .modal, .modal-dialog'
  )];
  return els.slice(0, 250).map((el) => ({
    tag: el.tagName,
    id: el.id || null,
    name: el.getAttribute('name'),
    type: el.getAttribute('type'),
    cls: (el.className && String(el.className).slice(0, 120)) || null,
    text: (el.innerText || el.textContent || '').trim().slice(0, 160),
    value: el.value !== undefined ? String(el.value).slice(0, 80) : null,
    visible: !!(el.offsetParent || el.getClientRects().length),
  }));
}
"""


def main() -> None:
    """Authenticate, open workspace, step into publish dialog, dump HTML."""
    if len(sys.argv) < 2:
        print("Usage: python debug\\dump_publish_dialog.py <datalumos_id>")
        sys.exit(1)

    workspace_id = sys.argv[1].strip()
    sys.argv = ["dump_publish_dialog", "publisher"]
    Args._initialized = False
    Args.initialize()
    Logger.initialize(log_level="INFO")
    Storage.initialize("StorageSQLLite", db_path=Path(Args.db_path))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    session = DataLumosBrowserSession()
    try:
        page = session.ensure_browser()
        session.ensure_authenticated()
        url = (
            f"https://www.datalumos.org/datalumos/workspace"
            f"?goToLevel=project&goToPath=/datalumos/{workspace_id}#"
        )
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=120000)

        from upload.DataLumosAuthenticator import wait_for_human_verification

        wait_for_human_verification(page, timeout=60000)

        publish = page.locator("button.btn-primary:has-text('Publish Project')")
        count = publish.count()
        print(f"Publish Project button count={count}")
        if count == 0:
            page.screenshot(path=str(OUT_DIR / "publish_no_button.png"), full_page=True)
            (OUT_DIR / "publish_workspace.html").write_text(
                page.content(), encoding="utf-8-sig"
            )
            print("No Publish Project button; dumped workspace HTML/screenshot")
            return

        print(f"visible={publish.first.is_visible()} text={publish.first.inner_text()!r}")
        publish.first.click()
        page.wait_for_url(lambda u: "reviewPublish" in u, timeout=120000)
        page.wait_for_timeout(1500)

        proceed = page.locator("button.btn-primary:has-text('Proceed to Publish')")
        print(f"Proceed count={proceed.count()} visible={proceed.first.is_visible()}")
        proceed.first.click()
        page.wait_for_timeout(3000)

        controls = page.evaluate(_dump_controls_js())
        out_json = OUT_DIR / "publish_dialog_controls.json"
        out_json.write_text(json.dumps(controls, indent=2), encoding="utf-8-sig")
        (OUT_DIR / "publish_dialog.html").write_text(
            page.content(), encoding="utf-8-sig"
        )
        page.screenshot(path=str(OUT_DIR / "publish_dialog.png"), full_page=True)
        print(f"Wrote {out_json}")
        for row in controls:
            if not row.get("visible"):
                continue
            blob = " ".join(
                str(row.get(k) or "")
                for k in ("id", "name", "type", "text", "cls")
            ).lower()
            if any(
                k in blob
                for k in (
                    "disclos",
                    "sensitive",
                    "deposit",
                    "license",
                    "delay",
                    "agree",
                    "publish",
                    "public",
                    "domain",
                )
            ):
                print(row)
    finally:
        session.close()
        Storage.reset()


if __name__ == "__main__":
    main()
