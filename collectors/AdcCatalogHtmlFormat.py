"""
Shared HTML formatting helpers for ARC catalog snapshots.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any


def escape_text(value: Any) -> str:
    """Escape a scalar value for HTML text nodes."""
    return html.escape(str(value).strip()) if value not in (None, "") else ""


def doi_url(doi: str) -> str:
    """Return a https DOI URL when a bare DOI is present."""
    doi = doi.strip()
    if not doi:
        return ""
    if doi.startswith("http"):
        return doi
    return f"https://doi.org/{doi}"


def link_or_text(url: str) -> str:
    """Return a hyperlink when ``url`` looks like a web address."""
    if not url:
        return ""
    safe = html.escape(url)
    if url.startswith("http"):
        return f'<a href="{safe}">{safe}</a>'
    return safe


def format_custom_value(value: Any) -> str:
    """Format a custom field value for HTML display."""
    if isinstance(value, list):
        text = ", ".join(str(item) for item in value if item)
        return html.escape(text)
    text = str(value).strip()
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
            pretty = json.dumps(parsed, indent=2)
            return f"<pre>{html.escape(pretty)}</pre>"
        except json.JSONDecodeError:
            pass
    return html.escape(text)


def table_section(title: str, rows: list[tuple[str, str]]) -> str:
    """Render a titled two-column metadata table."""
    body = "".join(
        f"<tr><th>{label}</th><td>{value}</td></tr>"
        for label, value in rows
        if value
    )
    if not body:
        return ""
    return f"<h2>{html.escape(title)}</h2><table>{body}</table>"


def list_section(title: str, items: list[str]) -> str:
    """Render a titled bullet list."""
    if not items:
        return ""
    body = "".join(f"<li>{item}</li>" for item in items if item)
    if not body:
        return ""
    return f"<h2>{html.escape(title)}</h2><ul>{body}</ul>"


def data_table(title: str, headers: list[str], rows: list[list[str]]) -> str:
    """Render a titled table with explicit column headers."""
    if not rows:
        return ""
    head = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
        if any(row)
    )
    if not body:
        return ""
    return (
        f"<h2>{html.escape(title)}</h2>"
        f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    )


def humanize_relation(relation: str) -> str:
    """Convert Figshare relation codes to readable labels."""
    mapping = {
        "IsSupplementTo": "Is supplement to",
        "IsSupplementedBy": "Is supplemented by",
        "IsReferencedBy": "Is referenced by",
        "References": "References",
        "IsPartOf": "Is part of",
        "HasPart": "Has part",
        "IsVersionOf": "Is version of",
        "IsNewVersionOf": "Is new version of",
        "IsIdenticalTo": "Is identical to",
    }
    if relation in mapping:
        return mapping[relation]
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", relation)
    return spaced.replace("_", " ").strip()
