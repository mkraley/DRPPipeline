"""
Extract Storage metadata fields from Figshare article JSON for ARC datasets.
"""

from __future__ import annotations

from typing import Any


def extract_metadata(article: dict[str, Any]) -> dict[str, str]:
    """
    Map a Figshare article document to Storage metadata fields.

    Args:
        article: Full Figshare article JSON from the public API.

    Returns:
        Dict with ``title``, ``summary``, and ``keywords`` when available.
    """
    tags = article.get("tags") or []
    keyword_parts: list[str] = []
    for tag in tags:
        if isinstance(tag, dict):
            keyword_parts.append(str(tag.get("name") or ""))
        else:
            keyword_parts.append(str(tag))
    keywords = ", ".join(part for part in keyword_parts if part)
    return {
        "title": str(article.get("title") or ""),
        "summary": str(article.get("description") or ""),
        "keywords": keywords,
    }
