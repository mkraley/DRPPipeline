"""
Open the real Clip and Ship details page and expand its field sections.

The explore landing page links to the full details with ``View Full Details``.
Field blocks use a ``chevronDown`` accordion, and some offer Chart or Table.
"""

from __future__ import annotations

import re
from contextlib import suppress
from typing import Any
from urllib.parse import urlparse

from utils.Logger import Logger

_FULL_DETAILS = re.compile(r"View\s+Full\s+Details", re.I)
_ALL_METADATA = re.compile(r"View\s+All\s+Metadata", re.I)
_SETTLE_MS = 2000
_NAV_TIMEOUT_MS = 90000

_HUB_SECTION_JS = """
() => {
  let clicked = 0;
  const clickEl = (el) => {
    if (!el) return false;
    const expanded = el.getAttribute && el.getAttribute("aria-expanded");
    if (expanded === "true") return false;
    try {
      el.scrollIntoView({ block: "center", behavior: "auto" });
      el.click();
      return true;
    } catch (_) {
      return false;
    }
  };
  const isClosedTable = (el) => {
    const label = (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();
    if (!/^table$/i.test(label)) return false;
    if (el.hasAttribute && el.hasAttribute("selected")) return false;
    if (el.getAttribute && el.getAttribute("aria-selected") === "true") return false;
    return true;
  };
  const walk = (root) => {
    const nodes = root.querySelectorAll ? root.querySelectorAll("*") : [];
    for (const el of nodes) {
      if (el.shadowRoot) walk(el.shadowRoot);
      const icon = (el.getAttribute && el.getAttribute("icon")) || "";
      if (icon === "chevronDown") {
        const host = (el.closest && el.closest("button, [role='button']")) || el;
        if (clickEl(host)) clicked++;
      }
      if ((el.tagName || "") === "CALCITE-TAB-TITLE" && isClosedTable(el)) {
        if (clickEl(el)) clicked++;
      }
    }
  };
  walk(document);
  return clicked;
}
"""


def open_real_landing_page(page: Any) -> bool:
    """
    Follow ``View Full Details`` when the Hub landing page offers it.

    A dataset explore page with no such control opens its about page instead.

    Args:
        page: Playwright page already on the landing URL.

    Returns:
        True when a different details page was opened.
    """
    if dataset_about_url(str(getattr(page, "url", "") or "")):
        _wait_for_full_details(page)
    if _click_full_details(page):
        _settle(page)
        return True
    about = dataset_about_url(str(getattr(page, "url", "") or ""))
    if not about:
        return False
    page.goto(about, wait_until="domcontentloaded", timeout=_NAV_TIMEOUT_MS)
    _settle(page)
    return True


def dataset_about_url(page_url: str) -> str | None:
    """
    Return the about URL for a dataset explore page.

    Args:
        page_url: Current page URL.

    Returns:
        About-page URL, or None when ``page_url`` is not a dataset explore page.
    """
    parsed = urlparse(page_url.strip())
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0].casefold() != "datasets":
        return None
    if parts[-1].casefold() == "about":
        return None
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}/datasets/{parts[1]}/about"


def metadata_page_url(page: Any) -> str | None:
    """
    Return the View All Metadata address when the details page links to it.

    Args:
        page: Playwright page on the full details view.

    Returns:
        Absolute metadata page URL, or None when the link is absent.
    """
    try:
        locator = page.get_by_role("link", name=_ALL_METADATA)
        if locator.count() < 1:
            return None
        href = str(locator.first.get_attribute("href") or "").strip()
    except Exception as exc:
        Logger.debug("View All Metadata lookup failed: %s", exc)
        return None
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return None


def expand_hub_field_sections(page: Any) -> int:
    """
    Open collapsed field accordions and choose Table over Chart.

    Args:
        page: Playwright page.

    Returns:
        Number of controls clicked, or 0 when the page cannot be scripted.
    """
    try:
        return max(int(page.evaluate(_HUB_SECTION_JS)), 0)
    except Exception as exc:
        Logger.debug("Hub field expand failed: %s", exc)
        return 0


def _wait_for_full_details(page: Any) -> None:
    """Wait until the explore page has rendered View Full Details."""
    with suppress(Exception):
        page.get_by_role("link", name=_FULL_DETAILS).first.wait_for(
            state="visible",
            timeout=15000,
        )


def _click_full_details(page: Any) -> bool:
    """Click the first visible View Full Details control."""
    for role in ("link", "button"):
        if _click_role(page, role):
            return True
    return False


def _click_role(page: Any, role: str) -> bool:
    """Click one visible control of ``role`` named View Full Details."""
    try:
        locator = page.get_by_role(role, name=_FULL_DETAILS)
        if locator.count() < 1:
            return False
        target = locator.first
        if target.is_visible() is not True:
            return False
        target.scroll_into_view_if_needed()
        target.click(timeout=5000)
        return True
    except Exception as exc:
        Logger.debug("View Full Details %s click failed: %s", role, exc)
        return False


def _settle(page: Any) -> None:
    """Wait for a Hub client-side navigation to finish rendering."""
    with suppress(Exception):
        page.wait_for_load_state("domcontentloaded", timeout=_NAV_TIMEOUT_MS)
    with suppress(Exception):
        page.wait_for_load_state("networkidle", timeout=30000)
    with suppress(Exception):
        page.wait_for_timeout(_SETTLE_MS)
