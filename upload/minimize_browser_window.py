"""Keep a headed Chromium window minimized without changing page layout."""

from __future__ import annotations

from playwright.sync_api import Frame, Page

from utils.Logger import Logger

AWAKE_WHEN_MINIMIZED_ARGS = [
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-background-timer-throttling",
]


def minimize_browser_window(page: Page) -> None:
    """Iconify the Chromium window that owns ``page``. Failures are ignored."""
    try:
        session = page.context.new_cdp_session(page)
        try:
            info = session.send("Browser.getWindowForTarget")
            session.send(
                "Browser.setWindowBounds",
                {
                    "windowId": info["windowId"],
                    "bounds": {"windowState": "minimized"},
                },
            )
        finally:
            session.detach()
    except Exception as exc:
        Logger.debug("Could not minimize browser window: %s", exc)


def keep_browser_window_minimized(page: Page) -> None:
    """Minimize now, and again after each main-frame navigation."""
    minimize_browser_window(page)
    page.on("framenavigated", lambda frame: _minimize_main_frame(page, frame))


def _minimize_main_frame(page: Page, frame: Frame) -> None:
    """Minimize when the navigated frame is the page's main frame."""
    if frame == page.main_frame:
        minimize_browser_window(page)
