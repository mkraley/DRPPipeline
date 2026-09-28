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
SkipTarget = Tuple[str, str, Optional[int], str]

SKIP_NOTE_MARKER = "Skipped download (>1GB)"

_SKIP_NOTE_RE = re.compile(
    r"Skipped download \(>1GB\):\s*(?P<name>.+?)\s*"
    r"\((?P<size>[^)]+)\)"
    r"(?:\s+in\s+(?P<folder>.+?))?"
    r"\s*-\s*download manually:\s*(?P<url>\S+)"
)
_SKIP_NOTE_NO_SIZE_RE = re.compile(
    r"Skipped download \(>1GB\):\s*(?P<name>.+?)"
    r"(?:\s+in\s+(?P<folder>.+?))?"
    r"\s*-\s*download manually:\s*(?P<url>\S+)"
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
    return [
        (name, url, size_bytes)
        for name, url, size_bytes, _folder in parse_skip_note_download_targets(status_notes)
    ]


def parse_skip_note_download_targets(
    status_notes: Optional[str],
) -> List[SkipTarget]:
    """
    Extract skip-note downloads, including an optional product subfolder.

    Returns ``(filename, url, size_bytes, relative_dir)``. ``relative_dir`` is
    empty when the note has no ``in <folder>`` clause.
    """
    if not status_notes:
        return []
    targets: List[SkipTarget] = []
    seen: set[tuple[str, str]] = set()
    remainder = status_notes
    for match in _SKIP_NOTE_RE.finditer(status_notes):
        target = _target_from_match(match, with_size=True)
        if target is None or (target[0], target[1]) in seen:
            continue
        seen.add((target[0], target[1]))
        targets.append(target)
        remainder = remainder.replace(match.group(0), "", 1)
    for match in _SKIP_NOTE_NO_SIZE_RE.finditer(remainder):
        target = _target_from_match(match, with_size=False)
        if target is None or (target[0], target[1]) in seen:
            continue
        seen.add((target[0], target[1]))
        targets.append(target)
    return targets


def _target_from_match(match: re.Match[str], *, with_size: bool) -> SkipTarget | None:
    """Build one skip target from a regex match."""
    name = match.group("name").strip()
    url = match.group("url").strip()
    if not name or not url:
        return None
    folder = (match.group("folder") or "").strip()
    size_bytes = parse_file_size_to_bytes(match.group("size").strip()) if with_size else None
    return name, url, size_bytes, folder
