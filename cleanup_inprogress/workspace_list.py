"""Parse DataLumos workspace sidebar entries."""

import re
from typing import Optional

PUBLISHED_MARK = "(Published)"
_ID_IN_TEXT = re.compile(r"datalumos-(\d+)")
_ID_IN_HREF = re.compile(r"/datalumos/(\d+)")
_ANCHOR_TEXT = re.compile(r"<a\b[^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")
PROJECT_URL = (
    "https://www.datalumos.org/datalumos/workspace"
    "?goToPath=/datalumos/{workspace_id}&goToLevel=project"
)


def workspace_id_from_entry(text: str, href: str = "") -> Optional[str]:
    """
    Return the DataLumos project id from sidebar text or href.

    Args:
        text: Visible label, often containing ``datalumos-<id>``.
        href: Link href, often containing ``/datalumos/<id>``.

    Returns:
        Numeric workspace id, or None when neither source has one.
    """
    match = _ID_IN_TEXT.search(text or "")
    if match:
        return match.group(1)
    match = _ID_IN_HREF.search(href or "")
    if match:
        return match.group(1)
    return None


def is_published_entry(text: str) -> bool:
    """
    Return True when the sidebar label is marked (Published).

    Args:
        text: Visible sidebar label.

    Returns:
        True when the label contains the published mark.
    """
    return PUBLISHED_MARK in (text or "")


def sidebar_labels(html: str) -> list[str]:
    """
    Return visible anchor labels from a workspace sidebar HTML fragment.

    Args:
        html: ``ul.list-group`` markup from the DataLumos workspace.

    Returns:
        Anchor texts in document order, with tags removed.
    """
    labels: list[str] = []
    for match in _ANCHOR_TEXT.finditer(html or ""):
        text = _TAGS.sub("", match.group(1)).replace("&amp;", "&").strip()
        if text:
            labels.append(text)
    return labels


def unpublished_workspace_ids(html: str) -> list[str]:
    """
    Return project ids whose sidebar label is not marked (Published).

    Args:
        html: ``ul.list-group`` markup from the DataLumos workspace.

    Returns:
        Numeric workspace ids, in sidebar order. The Workspace and
        Shared-with-me rows are omitted because they have no project id.
    """
    ids: list[str] = []
    for label in sidebar_labels(html):
        if is_published_entry(label):
            continue
        workspace_id = workspace_id_from_entry(label)
        if workspace_id:
            ids.append(workspace_id)
    return ids


def project_url(workspace_id: str) -> str:
    """
    Return a direct workspace URL for one project.

    Args:
        workspace_id: Numeric DataLumos project id.

    Returns:
        Workspace URL that opens that project.
    """
    return PROJECT_URL.format(workspace_id=workspace_id)
