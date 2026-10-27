"""Tests for PageExpandForPdf."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from collectors.PageExpandForPdf import (
    _click_playwright_arcgis_controls,
    expand_read_more_and_load_more,
)


class TestPageExpandForPdf(unittest.TestCase):
    """Tests for Read more / Load more expansion before PDF."""

    def test_stops_when_no_clicks(self) -> None:
        """Expansion stops after a round with zero clicks."""
        page = MagicMock()
        page.evaluate.return_value = 0
        with patch(
            "collectors.PageExpandForPdf._click_playwright_arcgis_controls",
            return_value=0,
        ):
            total = expand_read_more_and_load_more(page, max_rounds=5)
        self.assertEqual(total, 0)
        page.evaluate.assert_called_once()

    def test_loops_until_no_more_buttons(self) -> None:
        """Multiple rounds accumulate clicks until a zero round."""
        page = MagicMock()
        page.evaluate.side_effect = [2, 1, 0]
        with patch(
            "collectors.PageExpandForPdf._click_playwright_arcgis_controls",
            return_value=0,
        ):
            total = expand_read_more_and_load_more(
                page, max_rounds=10, round_wait_ms=1
            )
        self.assertEqual(total, 3)
        self.assertEqual(page.evaluate.call_count, 3)
        self.assertEqual(page.wait_for_timeout.call_count, 2)

    def test_respects_max_rounds(self) -> None:
        """Never exceeds max_rounds even if clicks keep appearing."""
        page = MagicMock()
        page.evaluate.return_value = 1
        with patch(
            "collectors.PageExpandForPdf._click_playwright_arcgis_controls",
            return_value=0,
        ):
            total = expand_read_more_and_load_more(
                page, max_rounds=3, round_wait_ms=1
            )
        self.assertEqual(total, 3)
        self.assertEqual(page.evaluate.call_count, 3)

    def test_includes_playwright_arcgis_clicks(self) -> None:
        """Playwright ArcGIS clicks are counted toward the total."""
        page = MagicMock()
        page.evaluate.side_effect = [0]
        with patch(
            "collectors.PageExpandForPdf._click_playwright_arcgis_controls",
            side_effect=[2, 0],
        ):
            total = expand_read_more_and_load_more(
                page, max_rounds=5, round_wait_ms=1
            )
        self.assertEqual(total, 2)

    def test_playwright_arcgis_noop_on_empty_page(self) -> None:
        """Playwright helper returns 0 when locators find nothing."""
        page = MagicMock()
        empty = MagicMock()
        empty.count.return_value = 0
        empty.filter.return_value = empty
        empty.is_visible.return_value = False
        page.locator.return_value = empty
        page.get_by_role.return_value = empty
        self.assertEqual(_click_playwright_arcgis_controls(page), 0)

    def test_playwright_clicks_more_button_and_calcite_link(self) -> None:
        """Clicks ArcGIS button.more-button and calcite-link Load more."""
        page = MagicMock()
        more = MagicMock()
        more.count.return_value = 1
        more_nth = MagicMock()
        more_nth.is_visible.return_value = True
        more.nth.return_value = more_nth

        load = MagicMock()
        load.count.return_value = 1
        load_nth = MagicMock()
        load_nth.is_visible.return_value = True
        load.nth.return_value = load_nth

        def locator_side_effect(selector: str, **_kwargs: object) -> MagicMock:
            if "more-button" in selector:
                return more
            link = MagicMock()
            link.filter.return_value = load
            return link

        page.locator.side_effect = locator_side_effect
        page.get_by_role.return_value = MagicMock(count=MagicMock(return_value=0))
        self.assertEqual(_click_playwright_arcgis_controls(page), 2)
        more_nth.click.assert_called_once()
        load_nth.click.assert_called_once()

    def test_live_browser_expands_arcgis_markup(self) -> None:
        """Live Chromium expands button.more-button and calcite-link Load more."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright not installed")

        html = """<!DOCTYPE html><html><body>
<div id="desc" style="display:none">FULL</div>
<button class="btn btn-link more-button" aria-expanded="false" type="button">
  Read More
</button>
<div id="items"><div>item1</div></div>
<calcite-link icon-end="chevron-down" role="presentation">Load more</calcite-link>
<script>
document.querySelector("button.more-button").addEventListener("click", function () {
  this.setAttribute("aria-expanded", "true");
  document.getElementById("desc").style.display = "block";
});
document.querySelector("calcite-link").addEventListener("click", function () {
  var d = document.createElement("div");
  d.textContent = "item2";
  document.getElementById("items").appendChild(d);
  this.remove();
});
</script>
</body></html>"""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content(html)
                clicks = expand_read_more_and_load_more(
                    page, max_rounds=5, round_wait_ms=100
                )
                state = page.evaluate(
                    """() => ({
                  ae: document.querySelector("button.more-button")
                    .getAttribute("aria-expanded"),
                  desc: getComputedStyle(document.getElementById("desc")).display,
                  items: document.querySelectorAll("#items div").length,
                  hasLm: !!document.querySelector("calcite-link"),
                })"""
                )
            finally:
                browser.close()

        self.assertGreaterEqual(clicks, 2)
        self.assertEqual(state["ae"], "true")
        self.assertEqual(state["desc"], "block")
        self.assertEqual(state["items"], 2)
        self.assertFalse(state["hasLm"])


if __name__ == "__main__":
    unittest.main()
