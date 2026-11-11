"""Tests for opening the real Clip and Ship details page."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from collectors.HubLandingPage import dataset_about_url, open_real_landing_page


class TestHubLandingPage(unittest.TestCase):
    """Tests for View Full Details and the dataset about fallback."""

    def test_clicks_view_full_details(self) -> None:
        """A visible full-details link is clicked and the explore URL stays."""
        page = MagicMock()
        link = MagicMock()
        link.count.return_value = 1
        link.first.is_visible.return_value = True
        page.get_by_role.return_value = link
        page.url = "https://edg-epa.hub.arcgis.com/datasets/abc/explore"

        self.assertTrue(open_real_landing_page(page))

        link.first.wait_for.assert_called_once()
        link.first.click.assert_called_once()
        page.goto.assert_not_called()

    def test_dataset_explore_without_button_opens_about(self) -> None:
        """Explore pages with no full-details control open the about page."""
        page = self._page_without_button(
            "https://edg-epa.hub.arcgis.com/datasets/abc/explore?showTable=true"
        )

        self.assertTrue(open_real_landing_page(page))

        self.assertEqual(
            page.goto.call_args.args[0],
            "https://edg-epa.hub.arcgis.com/datasets/abc/about",
        )

    def test_about_page_without_button_stays(self) -> None:
        """An about page is already the details page."""
        page = self._page_without_button(
            "https://edg-epa.hub.arcgis.com/datasets/abc_0/about"
        )
        self.assertFalse(open_real_landing_page(page))
        page.goto.assert_not_called()
        page.get_by_role.return_value.first.wait_for.assert_not_called()

    def test_dataset_about_url_ignores_other_sections(self) -> None:
        """Hub pages and documents are not rewritten to a dataset about URL."""
        self.assertIsNone(
            dataset_about_url("https://edg-epa.hub.arcgis.com/pages/abc")
        )
        self.assertIsNone(
            dataset_about_url("https://edg-epa.hub.arcgis.com/datasets/abc/about")
        )

    def _page_without_button(self, url: str) -> MagicMock:
        """Return a page whose View Full Details locators are empty."""
        page = MagicMock()
        empty = MagicMock()
        empty.count.return_value = 0
        page.get_by_role.return_value = empty
        page.url = url
        return page


if __name__ == "__main__":
    unittest.main()
