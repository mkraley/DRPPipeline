"""Tests for parsing NRC event-notification year indexes."""

import unittest

from scripts.event_notification_browser import (
    _REPORT_PRINT_CSS,
    _STRIP_INTERACTIVE_JS,
)
from scripts.event_notification_links import (
    links_for_month,
    looks_like_event_report,
    parse_day_links,
    year_index_url,
)
from scripts.collect_event_notifications import selected_months

_INDEX = """
<html><body>
<a href="/documents-reports/document-collections/events-reports-associated-with/event-notification-reports/2026/20260902en">Sep 2</a>
<a href="/documents-reports/document-collections/events-reports-associated-with/event-notification-reports/2026/20260901en">Sep 1</a>
<a href="/documents-reports/document-collections/events-reports-associated-with/event-notification-reports/2026/20260901en">Sep 1 again</a>
<a href="/documents-reports/document-collections/events-reports-associated-with/event-notification-reports/2026/20261001en">Oct 1</a>
<a href="/documents-reports/document-collections/events-reports-associated-with/event-notification-reports/2026/20260931en">bad</a>
<a href="/documents-reports/document-collections/events-reports-associated-with/event-notification-reports/2025">2025</a>
</body></html>
"""


class TestEventNotificationLinks(unittest.TestCase):
    """Year-index parsing keeps real day pages for the requested month."""

    def test_year_index_url(self) -> None:
        """The year index uses the reading-room path that still returns the day list."""
        self.assertEqual(
            year_index_url(2026),
            "https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2026/index",
        )

    def test_parse_day_links_drops_duplicates_and_invalid_dates(self) -> None:
        """Duplicate hrefs collapse and a non-existent day is ignored."""
        links = parse_day_links(_INDEX)
        self.assertEqual([link.filename for link in links], ["20260901en.pdf", "20260902en.pdf", "20261001en.pdf"])
        self.assertEqual(
            links[0].url,
            "https://www.nrc.gov/documents-reports/document-collections/events-reports-associated-with/event-notification-reports/2026/20260901en",
        )

    def test_links_for_month(self) -> None:
        """September 2026 keeps only that month."""
        chosen = links_for_month(parse_day_links(_INDEX), 2026, 9)
        self.assertEqual([link.day.day for link in chosen], [1, 2])

    def test_looks_like_event_report(self) -> None:
        """Akamai's denial page is rejected; a report title is accepted."""
        self.assertTrue(looks_like_event_report("<html>Event Notification Report</html>"))
        self.assertFalse(looks_like_event_report("<html>Access Denied edgesuite</html>"))

    def test_print_css_lets_the_report_flow_onto_later_pages(self) -> None:
        """Grid layout clipped the last page, and the body gradient did not paint there."""
        self.assertIn("overflow: visible", _REPORT_PRINT_CSS)
        self.assertIn(".grid.border", _REPORT_PRINT_CSS)
        self.assertIn("display: block", _REPORT_PRINT_CSS)
        self.assertIn("box-decoration-break: clone", _REPORT_PRINT_CSS)
        self.assertIn("background-color: #0d1225", _REPORT_PRINT_CSS)

    def test_strip_script_removes_form_controls_and_links(self) -> None:
        """Form controls and links are removed so the PDF has no fields or annotations."""
        self.assertIn("input, select, textarea, button", _STRIP_INTERACTIVE_JS)
        self.assertIn("replaceWith", _STRIP_INTERACTIVE_JS)

    def test_selected_months_covers_a_year_or_a_range(self) -> None:
        """Omitting the month selects all twelve; --through includes both ends."""
        self.assertEqual(selected_months(2026, 2026, 9), [(2026, 9)])
        self.assertEqual(len(selected_months(2024, 2024, None)), 12)
        self.assertEqual(selected_months(1999, 2000, None)[0], (1999, 1))
        self.assertEqual(selected_months(1999, 2000, None)[-1], (2000, 12))
