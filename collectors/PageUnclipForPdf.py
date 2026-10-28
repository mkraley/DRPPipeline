"""
Remove overflow / sticky / border clipping so Chromium print-to-PDF keeps text.

ArcGIS Hub (and similar SPAs) keep expanded ``Read more`` / ``Load more``
text inside scroll shells with ``overflow``, sticky chrome, and card borders.
Chromium then clips or redraws those frame edges at each page break, which
can obscure lines at the top and bottom of continued sections.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from utils.Logger import Logger

# Applied without @media print: SPA PDFs use emulate_media("screen").
_UNCLIP_CSS = """
html, body {
  height: auto !important;
  max-height: none !important;
  overflow: visible !important;
  position: static !important;
}
* {
  box-decoration-break: slice !important;
  -webkit-box-decoration-break: slice !important;
}
"""

# Tall framed panels get border edges redrawn at every page break.
_MIN_FRAME_HEIGHT_PX = 240

_UNCLIP_OVERFLOW_JS = """
(minFrameHeight) => {
  let touched = 0;
  const roots = [];

  const collectRoots = (root) => {
    if (!root || roots.includes(root)) return;
    roots.push(root);
    const nodes = root.querySelectorAll ? root.querySelectorAll("*") : [];
    for (const el of nodes) {
      if (el.shadowRoot) collectRoots(el.shadowRoot);
    }
  };
  collectRoots(document);

  const unlockBox = (el) => {
    try {
      el.style.setProperty("height", "auto", "important");
      el.style.setProperty("max-height", "none", "important");
      el.style.setProperty("overflow", "visible", "important");
      el.style.setProperty("overflow-x", "visible", "important");
      el.style.setProperty("overflow-y", "visible", "important");
      touched++;
    } catch (_) {}
  };

  const stripFrame = (el) => {
    try {
      el.style.setProperty("border", "none", "important");
      el.style.setProperty("border-width", "0", "important");
      el.style.setProperty("border-radius", "0", "important");
      el.style.setProperty("outline", "none", "important");
      el.style.setProperty("box-shadow", "none", "important");
      el.style.setProperty("filter", "none", "important");
      el.style.setProperty("mask-image", "none", "important");
      el.style.setProperty("-webkit-mask-image", "none", "important");
      el.style.setProperty("clip-path", "none", "important");
      el.style.setProperty("box-decoration-break", "slice", "important");
      el.style.setProperty("-webkit-box-decoration-break", "slice", "important");
      touched++;
    } catch (_) {}
  };

  const hasVisibleFrame = (st) => {
    const borderW =
      parseFloat(st.borderTopWidth) +
      parseFloat(st.borderBottomWidth) +
      parseFloat(st.borderLeftWidth) +
      parseFloat(st.borderRightWidth);
    const radius =
      parseFloat(st.borderTopLeftRadius) +
      parseFloat(st.borderTopRightRadius) +
      parseFloat(st.borderBottomLeftRadius) +
      parseFloat(st.borderBottomRightRadius);
    const shadow = st.boxShadow && st.boxShadow !== "none";
    const outline = parseFloat(st.outlineWidth) > 0 && st.outlineStyle !== "none";
    const mask =
      (st.maskImage && st.maskImage !== "none") ||
      (st.webkitMaskImage && st.webkitMaskImage !== "none");
    const clip = st.clipPath && st.clipPath !== "none";
    return borderW > 0 || radius > 0 || shadow || outline || mask || clip;
  };

  for (const root of roots) {
    const scope = root === document ? document.documentElement : root;
    const list = [];
    if (root === document) {
      list.push(document.documentElement, document.body);
    }
    if (scope && scope.querySelectorAll) {
      list.push(...scope.querySelectorAll("*"));
    }
    for (const el of list) {
      if (!el || el.nodeType !== 1) continue;
      let st;
      try {
        st = getComputedStyle(el);
      } catch (_) {
        continue;
      }
      const position = st.position;
      if (position === "fixed" || position === "sticky") {
        try {
          el.style.setProperty("position", "static", "important");
          touched++;
        } catch (_) {}
      }
      // Absolute bars pinned to top/bottom often paint over continued text.
      if (position === "absolute") {
        const top = st.top;
        const bottom = st.bottom;
        const pinnedTop = top === "0px" || top === "0";
        const pinnedBottom = bottom === "0px" || bottom === "0";
        const tall = el.getBoundingClientRect().height >= 8;
        const wide =
          el.getBoundingClientRect().width >=
          Math.min(document.documentElement.clientWidth, 320) * 0.5;
        if ((pinnedTop || pinnedBottom) && tall && wide) {
          try {
            el.style.setProperty("display", "none", "important");
            touched++;
            continue;
          } catch (_) {}
        }
      }
      const overflow =
        (st.overflow || "") +
        " " +
        (st.overflowY || "") +
        " " +
        (st.overflowX || "");
      const clips =
        /hidden|auto|scroll|overlay|clip/i.test(overflow) &&
        el.scrollHeight > el.clientHeight + 1;
      const clamped =
        st.webkitLineClamp &&
        st.webkitLineClamp !== "none" &&
        st.webkitLineClamp !== "";
      const capped =
        st.maxHeight &&
        st.maxHeight !== "none" &&
        st.maxHeight !== "0px" &&
        el.scrollHeight > el.clientHeight + 1;
      if (clips || clamped || capped) {
        unlockBox(el);
        stripFrame(el);
        if (clamped) {
          try {
            el.style.setProperty("-webkit-line-clamp", "unset", "important");
            el.style.setProperty("line-clamp", "unset", "important");
            el.style.setProperty("display", "block", "important");
          } catch (_) {}
        }
      }
      const boxHeight = Math.max(el.scrollHeight || 0, el.clientHeight || 0);
      if (boxHeight >= minFrameHeight && hasVisibleFrame(st)) {
        stripFrame(el);
      }
    }
  }
  return touched;
}
"""


def unclip_overflow_for_pdf(page: Any) -> int:
    """
    Lift overflow, frames, and sticky/fixed clipping for PDF.

    Args:
        page: Playwright page ready to print.

    Returns:
        Number of DOM style tweaks applied (0 when evaluation fails).
    """
    with suppress(Exception):
        page.add_style_tag(content=_UNCLIP_CSS)
    touched = 0
    try:
        touched = int(page.evaluate(_UNCLIP_OVERFLOW_JS, _MIN_FRAME_HEIGHT_PX))
    except Exception as exc:
        with suppress(Exception):
            Logger.debug("Unclip-for-PDF failed: %s", exc)
        return 0
    if touched > 0:
        with suppress(Exception):
            Logger.debug(
                "Unclipped %s overflow/frame/sticky node(s) before PDF", touched
            )
        with suppress(Exception):
            page.wait_for_timeout(300)
    return max(touched, 0)
