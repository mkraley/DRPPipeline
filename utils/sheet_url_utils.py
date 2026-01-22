"""
Utilities for parsing Google Sheets URLs.

Used by Sourcing to resolve spreadsheet ID and sheet gid from edit/export URLs.
"""

import re
from urllib.parse import parse_qs, urlparse


def parse_spreadsheet_url(url: str) -> tuple[str, str]:
    """
    Extract spreadsheet ID and sheet gid from a Google Sheets URL.

    Supports edit URLs (e.g. .../edit?gid=123#gid=123) and export URLs.
    If gid is absent, returns "0" (first sheet).

    Args:
        url: Google Sheets edit or export URL.

    Returns:
        (spreadsheet_id, gid) as strings.

    Raises:
        ValueError: If URL format is not recognized or ID cannot be extracted.

    Example:
        >>> parse_spreadsheet_url(
        ...     "https://docs.google.com/spreadsheets/d/ABC123/edit?gid=101637367"
        ... )
        ('ABC123', '101637367')
    """
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    if not match:
        raise ValueError(
            f"Could not extract spreadsheet ID from URL. "
            f"Expected pattern .../spreadsheets/d/{{id}}/... : {url[:80]}..."
        )
    sheet_id = match.group(1)

    parsed = urlparse(url)
    gid: str | None = None

    if parsed.query:
        qs = parse_qs(parsed.query)
        gids = qs.get("gid", [])
        if gids:
            gid = str(gids[0]).strip()
    if gid is None and parsed.fragment:
        frag = parsed.fragment
        if "gid=" in frag:
            parts = parse_qs(frag)
            gids = parts.get("gid", [])
            if gids:
                gid = str(gids[0]).strip()
    if gid is None:
        gid = "0"

    return (sheet_id, gid)
