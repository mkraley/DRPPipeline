"""Year ranges for Electric Quarterly Report CSV projects.

Each range stays under the 25 GiB resize line. Quarters from 2013 Q3 through
2026 Q3 belong to exactly one range.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

VIEWER_URL = "https://eqrreportviewer.ferc.gov/"
EXPLAIN_URL = (
    "https://www.ferc.gov/industries-data/electric/power-sales-and-markets/"
    "electric-quarterly-reports-eqr"
)
_VIEWER_HOST = "eqrreportviewer.ferc.gov"
_QUARTER = re.compile(r"^(\d{4})Q([1-4])$")
_ZIP_NAME = re.compile(r"^CSV_(\d{4})_Q([1-4])\.zip$", re.IGNORECASE)
_MONTH_START = {1: (1, 1), 2: (4, 1), 3: (7, 1), 4: (10, 1)}
_MONTH_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}


@dataclass(frozen=True)
class EqrProjectRange:
    """Inclusive span of EQR quarters stored as one pipeline project."""

    start_year: int
    start_quarter: int
    end_year: int
    end_quarter: int

    def contains(self, year: int, quarter: int) -> bool:
        """Return True when the quarter falls inside this span."""
        return _quarter_index(self.start_year, self.start_quarter) <= _quarter_index(
            year, quarter
        ) <= _quarter_index(self.end_year, self.end_quarter)

    def source_url(self) -> str:
        """Return the viewer URL that encodes this span."""
        start = f"{self.start_year}Q{self.start_quarter}"
        end = f"{self.end_year}Q{self.end_quarter}"
        return f"{VIEWER_URL}?start={start}&end={end}"

    def label(self) -> str:
        """Return the year span used in the project title."""
        return _span_label(
            self.start_year,
            self.start_quarter,
            self.end_year,
            self.end_quarter,
        )

    def title(self) -> str:
        """Return the DataLumos title for this span."""
        return f"Electric Quarterly Report (CSV), {self.label()}"

    def summary(self) -> str:
        """Return a description of the CSV zips in this span."""
        return (
            f"Electric Quarterly Report CSV filings for {self.label()}. "
            "Each quarterly zip holds per-company filings of contract terms and "
            "wholesale power sales, including market-based and cost-based sales "
            "and transmission service. XML copies are not included."
        )

    def time_start(self) -> str:
        """Return the first day of the opening quarter as YYYY-MM-DD."""
        month, day = _MONTH_START[self.start_quarter]
        return f"{self.start_year:04d}-{month:02d}-{day:02d}"

    def time_end(self) -> str:
        """Return the last day of the closing quarter as YYYY-MM-DD."""
        month, day = _MONTH_END[self.end_quarter]
        return f"{self.end_year:04d}-{month:02d}-{day:02d}"


def project_ranges() -> tuple[EqrProjectRange, ...]:
    """Return the seven EQR projects, each under 25 GiB at the measured sizes."""
    return (
        EqrProjectRange(2013, 3, 2018, 4),
        EqrProjectRange(2019, 1, 2020, 4),
        EqrProjectRange(2021, 1, 2021, 4),
        EqrProjectRange(2022, 1, 2022, 4),
        EqrProjectRange(2023, 1, 2023, 4),
        EqrProjectRange(2024, 1, 2024, 4),
        EqrProjectRange(2025, 1, 2026, 3),
    )


def range_from_source_url(url: str) -> EqrProjectRange | None:
    """
    Parse an EQR project URL.

    Args:
        url: Stored source URL.

    Returns:
        The span, or None when the URL is not an EQR project.
    """
    parsed = urlparse(url.strip())
    if parsed.netloc.lower() != _VIEWER_HOST:
        return None
    query = parse_qs(parsed.query)
    start = _quarter_token(query.get("start"))
    end = _quarter_token(query.get("end"))
    if start is None or end is None:
        return None
    if _quarter_index(*start) > _quarter_index(*end):
        return None
    return EqrProjectRange(start[0], start[1], end[0], end[1])


def quarter_from_zip_name(name: str) -> tuple[int, int] | None:
    """Return ``(year, quarter)`` for ``CSV_YYYY_Q#.zip``."""
    match = _ZIP_NAME.match(name.strip())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def _quarter_token(values: list[str] | None) -> tuple[int, int] | None:
    """Parse one ``YYYYQ#`` query value."""
    if not values:
        return None
    match = _QUARTER.match(values[0].strip())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def _quarter_index(year: int, quarter: int) -> int:
    """Return a comparable index for a calendar quarter."""
    return year * 4 + quarter


def _span_label(start_year: int, start_quarter: int, end_year: int, end_quarter: int) -> str:
    """Format a quarter span for a title."""
    if start_year == end_year and start_quarter == 1 and end_quarter == 4:
        return str(start_year)
    if (start_year, start_quarter) == (end_year, end_quarter):
        return f"{start_year} Q{start_quarter}"
    if start_quarter == 1 and end_quarter == 4:
        return f"{start_year}–{end_year}"
    if start_quarter == 1:
        return f"{start_year}–{end_year} Q{end_quarter}"
    if end_quarter == 4:
        return f"{start_year} Q{start_quarter}–{end_year}"
    return f"{start_year} Q{start_quarter}–{end_year} Q{end_quarter}"
