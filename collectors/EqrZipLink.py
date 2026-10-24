"""CSV quarterly zip links from the EQR report viewer."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

from collectors.EqrProjectRange import VIEWER_URL, EqrProjectRange, quarter_from_zip_name

_CSV_NAME = re.compile(r"CSV_(\d{4})_Q([1-4])\.zip", re.IGNORECASE)


@dataclass(frozen=True)
class EqrZipLink:
    """One quarterly CSV zip advertised by the viewer."""

    name: str
    url: str
    size_bytes: int | None = None

    def with_size(self, size_bytes: int) -> "EqrZipLink":
        """Return a copy that records the archive size."""
        return EqrZipLink(self.name, self.url, size_bytes)


def csv_links_from_pairs(pairs: list[tuple[str, str]]) -> list[EqrZipLink]:
    """
    Keep quarterly CSV zip anchors and drop the XML copies.

    Args:
        pairs: ``(text, href)`` from the viewer download table.

    Returns:
        CSV zips in chronological file-name order.
    """
    found: dict[str, EqrZipLink] = {}
    for text, href in pairs:
        link = _link_from_anchor(text, href)
        if link is not None:
            found[link.name] = link
    return [found[name] for name in sorted(found)]


def links_for_range(links: list[EqrZipLink], span: EqrProjectRange) -> list[EqrZipLink]:
    """Return the CSV zips whose quarter falls in ``span``."""
    selected: list[EqrZipLink] = []
    for link in links:
        quarter = quarter_from_zip_name(link.name)
        if quarter is not None and span.contains(*quarter):
            selected.append(link)
    return selected


def _link_from_anchor(text: str, href: str) -> EqrZipLink | None:
    """Return a CSV zip link when the anchor points at one."""
    if "/XML/" in href.upper():
        return None
    match = _CSV_NAME.search(href) or _CSV_NAME.search(text)
    if match is None:
        return None
    if href and "/CSV/" not in href and not text.upper().startswith("CSV_"):
        return None
    name = f"CSV_{match.group(1)}_Q{match.group(2)}.zip"
    url = href if href.lower().startswith("http") else urljoin(VIEWER_URL, href)
    return EqrZipLink(name, url)
