"""Tests for EQR year-range projects."""

from __future__ import annotations

import unittest

from collectors.EqrProjectRange import project_ranges, range_from_source_url


class TestEqrProjectRange(unittest.TestCase):
    """The seven spans partition 2013 Q3 through 2026 Q3."""

    def test_ranges_match_the_agreed_split(self) -> None:
        """Whole years stay together, and no span crosses the 25 GiB line."""
        bounds = [
            (item.start_year, item.start_quarter, item.end_year, item.end_quarter)
            for item in project_ranges()
        ]
        self.assertEqual(
            bounds,
            [
                (2013, 3, 2018, 4),
                (2019, 1, 2020, 4),
                (2021, 1, 2021, 4),
                (2022, 1, 2022, 4),
                (2023, 1, 2023, 4),
                (2024, 1, 2024, 4),
                (2025, 1, 2026, 3),
            ],
        )

    def test_every_collected_quarter_belongs_to_one_project(self) -> None:
        """2013 Q2 and 2026 Q4 are outside the snapshot."""
        quarters = _quarters(2013, 3, 2026, 3)
        for year, quarter in quarters:
            owners = [item for item in project_ranges() if item.contains(year, quarter)]
            self.assertEqual(len(owners), 1, f"{year} Q{quarter}")
        self.assertFalse(project_ranges()[0].contains(2013, 2))
        self.assertFalse(project_ranges()[-1].contains(2026, 4))

    def test_titles_and_dates_follow_the_span(self) -> None:
        """Partial spans name the open quarter, and a full year is just the year."""
        ranges = project_ranges()
        self.assertEqual(ranges[0].title(), "Electric Quarterly Report (CSV), 2013 Q3–2018")
        self.assertEqual(ranges[2].title(), "Electric Quarterly Report (CSV), 2021")
        self.assertEqual(ranges[1].title(), "Electric Quarterly Report (CSV), 2019–2020")
        self.assertEqual(ranges[-1].title(), "Electric Quarterly Report (CSV), 2025–2026 Q3")
        self.assertEqual(ranges[0].time_start(), "2013-07-01")
        self.assertEqual(ranges[0].time_end(), "2018-12-31")
        self.assertEqual(ranges[-1].time_end(), "2026-09-30")

    def test_source_url_round_trip(self) -> None:
        """The stored URL is the span the collector reads back."""
        span = project_ranges()[0]
        parsed = range_from_source_url(span.source_url())
        self.assertEqual(parsed, span)
        self.assertIsNone(range_from_source_url("https://data.ferc.gov/form-552/master"))
        self.assertIsNone(range_from_source_url("https://eqrreportviewer.ferc.gov/"))


def _quarters(start_year: int, start_quarter: int, end_year: int, end_quarter: int) -> list[tuple[int, int]]:
    """Return inclusive quarters from the start through the end."""
    quarters: list[tuple[int, int]] = []
    year, quarter = start_year, start_quarter
    while (year, quarter) <= (end_year, end_quarter):
        quarters.append((year, quarter))
        quarter += 1
        if quarter == 5:
            year += 1
            quarter = 1
    return quarters


if __name__ == "__main__":
    unittest.main()
