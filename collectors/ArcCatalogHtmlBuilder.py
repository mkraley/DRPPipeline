"""
Build an HTML catalog detail page from Figshare API metadata for ARC datasets.

Ag Data Commons portal pages are a JavaScript SPA behind AWS WAF; they do not
archive well as static HTML or print cleanly to PDF. This module renders a
standalone catalog snapshot from the public Figshare API JSON instead (same role
as server-rendered HTML for the USFS collector).
"""

from __future__ import annotations

import html
from typing import Any

from collectors import ArcCatalogHtmlSections as sections


def build_catalog_html(article: dict[str, Any], source_url: str) -> str:
    """
    Render a catalog detail HTML document from a Figshare article payload.

    Args:
        article: Full Figshare article JSON.
        source_url: Original Ag Data Commons portal URL for the record.

    Returns:
        Complete HTML document string.
    """
    title = html.escape(str(article.get("title") or "Untitled"))
    body_parts = [
        sections.page_header(source_url),
        f"<h1>{title}</h1>",
        sections.authors_section(article),
        sections.record_metadata_section(article, source_url),
        sections.categories_section(article),
        sections.keywords_section(article),
        sections.description_section(article),
        sections.custom_fields_section(article),
        sections.funding_section(article),
        sections.related_materials_section(article),
        sections.references_section(article),
        sections.history_section(article),
        sections.files_section(article),
        sections.page_footer(),
    ]
    return _wrap_document(title, body_parts)


def _wrap_document(title: str, body_parts: list[str]) -> str:
    """Wrap body fragments in a styled HTML document."""
    body = "\n".join(part for part in body_parts if part)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>
    body {{ font-family: Georgia, "Times New Roman", serif; margin: 2em; color: #222; }}
    h1 {{ font-size: 1.5em; margin-bottom: 0.25em; }}
    h2 {{ font-size: 1.1em; margin-top: 1.5em; border-bottom: 1px solid #ccc; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 0.5em; }}
    th, td {{ border: 1px solid #ddd; padding: 0.4em 0.6em; text-align: left; vertical-align: top; }}
    th {{ background: #f5f5f5; }}
    thead th {{ width: auto; }}
    table tr > th:first-child {{ width: 30%; }}
    ul {{ margin-top: 0.5em; }}
    .meta-note {{ color: #555; font-size: 0.9em; margin-bottom: 1.5em; }}
    .description {{ line-height: 1.5; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #fafafa; padding: 0.5em; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""
