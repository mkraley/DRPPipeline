"""Tests for PageUnclipForPdf."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from collectors.PageUnclipForPdf import _MIN_FRAME_HEIGHT_PX, unclip_overflow_for_pdf


class TestPageUnclipForPdf(unittest.TestCase):
    """Tests for overflow / sticky unclip before PDF."""

    def test_injects_css_and_evaluates_unclip(self) -> None:
        """Adds unclip CSS and runs the overflow-lifting script."""
        page = MagicMock()
        page.evaluate.return_value = 4
        touched = unclip_overflow_for_pdf(page)
        self.assertEqual(touched, 4)
        page.add_style_tag.assert_called_once()
        css = page.add_style_tag.call_args.kwargs["content"]
        self.assertIn("overflow: visible", css)
        self.assertIn("box-decoration-break: slice", css)
        page.evaluate.assert_called_once()
        self.assertEqual(
            page.evaluate.call_args.args[1],
            _MIN_FRAME_HEIGHT_PX,
        )
        page.wait_for_timeout.assert_called()

    def test_returns_zero_when_evaluate_fails(self) -> None:
        """Evaluation errors yield 0 without raising."""
        page = MagicMock()
        page.evaluate.side_effect = RuntimeError("boom")
        self.assertEqual(unclip_overflow_for_pdf(page), 0)

    def test_live_browser_lifts_overflow_hidden_clip(self) -> None:
        """Live Chromium removes overflow:hidden so clipped text is measurable."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright not installed")

        html = """<!DOCTYPE html><html><body>
<div id="clip" style="max-height:40px; overflow:hidden; border:1px solid #000;">
<p>line1</p><p>line2</p><p>line3</p><p>line4</p><p>line5</p>
<p>line6</p><p>line7</p><p>line8</p>
</div>
<div id="sticky" style="position:sticky; top:0; height:20px;">sticky-bar</div>
</body></html>"""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content(html)
                before = page.evaluate(
                    """() => {
                  const el = document.getElementById("clip");
                  return {
                    overflow: getComputedStyle(el).overflow,
                    clipped: el.scrollHeight > el.clientHeight + 1,
                    borderTop: getComputedStyle(el).borderTopWidth,
                  };
                }"""
                )
                touched = unclip_overflow_for_pdf(page)
                after = page.evaluate(
                    """() => {
                  const el = document.getElementById("clip");
                  const sticky = document.getElementById("sticky");
                  return {
                    overflow: getComputedStyle(el).overflow,
                    clipped: el.scrollHeight > el.clientHeight + 1,
                    stickyPosition: getComputedStyle(sticky).position,
                    borderTop: getComputedStyle(el).borderTopWidth,
                  };
                }"""
                )
            finally:
                browser.close()

        self.assertTrue(before["clipped"])
        self.assertGreater(touched, 0)
        self.assertEqual(after["overflow"], "visible")
        self.assertFalse(after["clipped"])
        self.assertEqual(after["stickyPosition"], "static")
        self.assertEqual(after["borderTop"], "0px")

    def test_live_browser_strips_tall_panel_frame(self) -> None:
        """Tall bordered panels lose frame edges that redraw at page breaks."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright not installed")

        paragraphs = "".join(f"<p>paragraph {i} content line</p>" for i in range(40))
        html = f"""<!DOCTYPE html><html><body>
<section id="panel" style="border:2px solid #333; border-radius:8px;
  box-shadow:0 2px 8px rgba(0,0,0,.3); padding:12px;">
{paragraphs}
</section>
<div id="edge" style="position:absolute; top:0; left:0; right:0; height:24px;
  width:100%; background:#eee;">top-bar</div>
</body></html>"""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content(html)
                before = page.evaluate(
                    """() => {
                  const el = document.getElementById("panel");
                  const st = getComputedStyle(el);
                  return {
                    border: st.borderTopWidth,
                    shadow: st.boxShadow,
                    radius: st.borderTopLeftRadius,
                  };
                }"""
                )
                unclip_overflow_for_pdf(page)
                after = page.evaluate(
                    """() => {
                  const el = document.getElementById("panel");
                  const edge = document.getElementById("edge");
                  const st = getComputedStyle(el);
                  return {
                    border: st.borderTopWidth,
                    shadow: st.boxShadow,
                    radius: st.borderTopLeftRadius,
                    edgeDisplay: getComputedStyle(edge).display,
                  };
                }"""
                )
            finally:
                browser.close()

        self.assertNotEqual(before["border"], "0px")
        self.assertEqual(after["border"], "0px")
        self.assertEqual(after["shadow"], "none")
        self.assertEqual(after["radius"], "0px")
        self.assertEqual(after["edgeDisplay"], "none")


if __name__ == "__main__":
    unittest.main()
