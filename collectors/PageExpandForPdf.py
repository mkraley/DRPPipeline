"""
Expand truncated page content before print-to-PDF capture.

Clicks visible ``Read more``, ``Load more``, and short ``Show more`` controls
(Socrata, ArcGIS Hub/item pages, CMS patterns).
"""

from __future__ import annotations

import re
from contextlib import suppress
from typing import Any

from utils.Logger import Logger

_DEFAULT_MAX_ROUNDS = 20
_ROUND_WAIT_MS = 750

# ArcGIS Hub: button.more-button ("Read More"); calcite-link ("Load more").
# Prefer a single .click() — dual dispatch+click toggles Ember "Read More" shut.
_CLICK_EXPAND_ROUND_JS = """
() => {
  let clicked = 0;
  const norm = (s) => (s || "").replace(/[\\s\\u00a0]+/g, " ").trim();
  const visible = (el) => {
    if (!el || !el.getBoundingClientRect) return false;
    const st = getComputedStyle(el);
    if (st.display === "none" || st.visibility === "hidden" || st.opacity === "0") {
      return false;
    }
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const labelOf = (el) => {
    const parts = [
      el.getAttribute && el.getAttribute("aria-label"),
      el.getAttribute && el.getAttribute("title"),
      el.innerText,
      el.textContent,
    ]
      .map((s) => norm(s))
      .filter(Boolean);
    // Prefer shortest non-empty label so SVG/noise does not inflate length.
    parts.sort((a, b) => a.length - b.length);
    return parts[0] || "";
  };
  const isCollapse = (t) => /\\b(read|show|load)\\s+less\\b/i.test(t);
  const isReadMore = (t) => /\\bread\\s+more\\b/i.test(t);
  const isLoadMore = (t) => /\\bload\\s+more\\b/i.test(t);
  const isShowMore = (t) =>
    /^show\\s+more(\\s*\\(|$)/i.test(t) || /^show\\s+more$/i.test(t);
  const shouldExpand = (t) =>
    Boolean(
      t &&
        t.length <= 80 &&
        !isCollapse(t) &&
        (isReadMore(t) || isLoadMore(t) || isShowMore(t))
    );
  const alreadyExpanded = (el) => {
    const ae = el.getAttribute && el.getAttribute("aria-expanded");
    return ae === "true";
  };
  const clickEl = (el) => {
    if (!visible(el) || alreadyExpanded(el)) return false;
    try {
      el.scrollIntoView({ block: "center", behavior: "auto" });
      if (typeof el.click === "function") {
        el.click();
      } else {
        el.dispatchEvent(
          new MouseEvent("click", { bubbles: true, cancelable: true, view: window })
        );
      }
      return true;
    } catch (_) {
      return false;
    }
  };

  for (const el of document.querySelectorAll("button.more-button")) {
    if (clickEl(el)) clicked++;
  }
  for (const el of document.querySelectorAll("calcite-link")) {
    const t = labelOf(el);
    if (!shouldExpand(t)) continue;
    if (clickEl(el)) clicked++;
  }
  for (const el of document.querySelectorAll("forge-button.collapse-button")) {
    if (clickEl(el)) clicked++;
  }
  const candidates = document.querySelectorAll(
    "button, a, calcite-button, calcite-link, [role='button']"
  );
  for (const el of candidates) {
    if (el.matches && el.matches("button.more-button, calcite-link")) {
      continue;
    }
    const t = labelOf(el);
    if (!shouldExpand(t)) continue;
    if (clickEl(el)) clicked++;
  }
  return clicked;
}
"""


def _locator_count(locator: Any) -> int:
    """Return a non-negative locator count, or 0 if unavailable."""
    try:
        value = locator.count()
        return max(int(value), 0)
    except Exception:
        return 0


def _click_visible_locator(locator: Any, *, label: str) -> bool:
    """Scroll to and click a visible locator; return True on success."""
    try:
        if locator.is_visible() is not True:
            return False
        locator.scroll_into_view_if_needed()
        locator.click(timeout=3000)
        return True
    except Exception as exc:
        Logger.debug("Playwright %s click failed: %s", label, exc)
        return False


def _click_playwright_arcgis_controls(page: Any) -> int:
    """
    Click ArcGIS Hub Read More / Load more via Playwright (pierces shadow DOM).

    Returns:
        Number of successful clicks this pass.
    """
    clicked = 0
    more_buttons = page.locator("button.more-button:not([aria-expanded='true'])")
    for index in range(_locator_count(more_buttons)):
        if _click_visible_locator(more_buttons.nth(index), label="Read More"):
            clicked += 1

    load_clicked = 0
    load_more = page.locator("calcite-link").filter(
        has_text=re.compile(r"Load\s+more", re.I)
    )
    for index in range(_locator_count(load_more)):
        if _click_visible_locator(load_more.nth(index), label="Load more"):
            load_clicked += 1

    # Shadow-piercing fallback when host role is presentation and host click missed.
    if load_clicked == 0:
        by_role = page.get_by_role("button", name=re.compile(r"Load\s+more", re.I))
        for index in range(_locator_count(by_role)):
            if _click_visible_locator(by_role.nth(index), label="role Load more"):
                load_clicked += 1

    clicked += load_clicked
    return clicked


def expand_read_more_and_load_more(
    page: Any,
    *,
    max_rounds: int = _DEFAULT_MAX_ROUNDS,
    round_wait_ms: int = _ROUND_WAIT_MS,
) -> int:
    """
    Click ``Read more`` / ``Load more`` (and short ``Show more``) until stable.

    Args:
        page: Playwright page with loaded document.
        max_rounds: Maximum click rounds (content may load asynchronously).
        round_wait_ms: Pause between rounds after clicks.

    Returns:
        Total number of control clicks performed.
    """
    total = 0
    for round_index in range(max_rounds):
        round_clicks = 0
        pw_clicks = 0
        try:
            pw_clicks = _click_playwright_arcgis_controls(page)
            round_clicks += pw_clicks
        except Exception as exc:
            Logger.debug(
                "Playwright expand-for-PDF round %s failed: %s",
                round_index + 1,
                exc,
            )
        # JS covers Socrata/generic controls; also falls back if Playwright
        # missed ArcGIS hosts. Skip when Playwright already clicked this round
        # so Ember "Read More" is not toggled shut by a second click.
        if pw_clicks == 0:
            try:
                round_clicks += int(page.evaluate(_CLICK_EXPAND_ROUND_JS))
            except Exception as exc:
                Logger.debug(
                    "Expand-for-PDF JS round %s failed: %s",
                    round_index + 1,
                    exc,
                )
                if round_clicks <= 0:
                    break
        total += max(round_clicks, 0)
        if round_clicks <= 0:
            break
        page.wait_for_timeout(round_wait_ms)
    if total > 0:
        with suppress(Exception):
            Logger.debug(
                "Expanded %s Read more / Load more control(s) before PDF", total
            )
    return total
