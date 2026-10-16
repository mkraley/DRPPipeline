"""Parse NRC daily event-notification links from a year index page."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

NRC_ORIGIN = "https://www.nrc.gov"
_YEAR_INDEX = (
    "https://www.nrc.gov/reading-rm/doc-collections/event-status/event/{year}/index"
)
_DAY_HREF = re.compile(
    r"/event-notification-reports/(?P<year>\d{4})/(?P<stamp>\d{8})en/?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EventDayLink:
    """One daily event-notification page listed on a year index."""

    day: date
    url: str
    filename: str


def year_index_url(year: int) -> str:
    """Return the NRC year index that lists that year's daily reports."""
    return _YEAR_INDEX.format(year=year)


def parse_day_links(html: str) -> list[EventDayLink]:
    """
    Return unique daily report links from year-index HTML, oldest first.

    Ignores year links and stamps that are not real calendar dates.
    """
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, EventDayLink] = {}
    for anchor in soup.find_all("a", href=True):
        link = _link_from_href(str(anchor["href"]))
        if link is not None:
            found[link.filename] = link
    return sorted(found.values(), key=lambda item: item.day)


def links_for_month(links: list[EventDayLink], year: int, month: int) -> list[EventDayLink]:
    """Keep links whose date falls in ``year`` and ``month``."""
    return [link for link in links if link.day.year == year and link.day.month == month]


def looks_like_event_report(html: str) -> bool:
    """Return True when HTML is a report page rather than an Akamai block."""
    if "Access Denied" in html and "edgesuite" in html:
        return False
    return "Event Notification" in html


def _link_from_href(href: str) -> EventDayLink | None:
    """Build a day link from an anchor href, or None when it is not a day page."""
    path = href.split("?", 1)[0].strip()
    match = _DAY_HREF.search(path)
    if match is None:
        return None
    stamp = match.group("stamp")
    try:
        day = datetime.strptime(stamp, "%Y%m%d").date()
    except ValueError:
        return None
    if day.year != int(match.group("year")):
        return None
    return EventDayLink(day=day, url=urljoin(NRC_ORIGIN, path), filename=f"{stamp}en.pdf")
