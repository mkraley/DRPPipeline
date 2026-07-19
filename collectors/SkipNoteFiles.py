"""
Parse collector "Skipped download (>1GB)" status_notes into publication-file tuples.

Both ``UsfsCollector`` and ``AdcCollector`` record large files they did not
download as ``status_notes`` lines of the form::

    Skipped download (>1GB): NAME (SIZE) - download manually: URL

This module turns those lines back into ``(filename, url, size_bytes)`` tuples so
the aria2 export/download tooling can fetch them later, regardless of the source
site (USFS Research Data Archive, Ag Data Commons/Figshare, etc.).
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from utils.file_utils import parse_file_size_to_bytes

PublicationFile = Tuple[str, str, Optional[int]]

SKIP_NOTE_MARKER = "Skipped download (>1GB)"

_SKIP_NOTE_RE = re.compile(
    r"Skipped download \(>1GB\):\s*(?P<name>.+?)\s*"
    r"\((?P<size>[^)]+)\)\s*-\s*download manually:\s*(?P<url>\S+)"
)


def parse_skip_note_publication_files(
    status_notes: Optional[str],
) -> List[PublicationFile]:
    """
    Extract skipped large-file entries from a project's ``status_notes``.

    Args:
        status_notes: Raw ``status_notes`` text (may be None or empty).

    Returns:
        List of ``(filename, url, size_bytes)`` tuples, one per skip line.
        ``size_bytes`` is None when the size token cannot be parsed.
    """
    if not status_notes:
        return []
    files: List[PublicationFile] = []
    for match in _SKIP_NOTE_RE.finditer(status_notes):
        name = match.group("name").strip()
        url = match.group("url").strip()
        size_bytes = parse_file_size_to_bytes(match.group("size").strip())
        files.append((name, url, size_bytes))
    return files
