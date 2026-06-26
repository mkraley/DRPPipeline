"""
Normalize dataset summary HTML for DataLumos wysihtml5 and clipboard paste.

Figshare and other sources often include attributes and tags that wysihtml5
drops or treats as plain text. This module keeps a small semantic subset and
strips presentation-only markup.
"""

from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup, Tag

_ALLOWED_TAGS = frozenset({
    "a",
    "b",
    "blockquote",
    "br",
    "em",
    "h1",
    "h2",
    "h3",
    "i",
    "li",
    "ol",
    "p",
    "strong",
    "sub",
    "sup",
    "u",
    "ul",
})
_BLOCK_TAGS = frozenset({"p", "h1", "h2", "h3", "blockquote", "ul", "ol", "li"})


def prepare_summary_for_datalumos_upload(summary: str) -> str:
    """
    Prepare a stored summary for the DataLumos wysihtml5 description field.

    Decodes entity-escaped HTML, normalizes tags, then restructures block elements
    into a single paragraph with ``<br><br>`` separators so wysihtml5 preserves
    paragraph breaks on save.

    Args:
        summary: Raw summary from Storage or the interactive collector.

    Returns:
        HTML string suitable for programmatic editor fill.
    """
    decoded = decode_summary_html_entities(summary)
    normalized = normalize_summary_html_for_datalumos(decoded)
    return structure_summary_for_wysihtml5(normalized)


def decode_summary_html_entities(summary: str) -> str:
    """
    Decode HTML entity-encoded summaries (e.g. ``&lt;p&gt;``) from database exports.

    Repeatedly unescapes while the value still looks like escaped markup.

    Args:
        summary: Raw summary text.

    Returns:
        Decoded summary string.
    """
    text = (summary or "").strip()
    while _looks_like_escaped_html(text):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    return text


def structure_summary_for_wysihtml5(normalized_html: str) -> str:
    """
    Restructure block HTML for wysihtml5 editors that collapse adjacent ``<p>`` tags.

    Inline markup (links, bold, etc.) is preserved inside each block. Multiple blocks
    are joined with ``<br><br>`` inside one ``<p>`` so line breaks survive save.

    Args:
        normalized_html: Output from :func:`normalize_summary_html_for_datalumos`.

    Returns:
        HTML tuned for wysihtml5 persistence.
    """
    text = (normalized_html or "").strip()
    if not text or "<" not in text:
        return text

    soup = BeautifulSoup(text, "html.parser")
    blocks: list[str] = []
    for element in soup.find_all(["p", "h1", "h2", "h3", "blockquote", "li"]):
        if element.name in {"h1", "h2", "h3"}:
            inner = element.decode_contents().strip()
            if inner:
                blocks.append(f"<strong>{inner}</strong>")
            continue
        inner = element.decode_contents().strip()
        if inner:
            blocks.append(inner)

    if len(blocks) >= 2:
        return f"<p>{'<br><br>'.join(blocks)}</p>"
    if len(blocks) == 1:
        return f"<p>{blocks[0]}</p>"
    return text


def normalize_summary_html_for_datalumos(summary: str) -> str:
    """
    Return wysihtml5-friendly HTML for the DataLumos description field.

    Plain text is wrapped in a paragraph. Existing HTML is cleaned to a small
    tag whitelist with only ``href`` preserved on links.

    Args:
        summary: Raw summary HTML or plain text from storage.

    Returns:
        Normalized HTML string, or empty when input is blank.
    """
    text = (summary or "").strip()
    if not text:
        return ""

    text = decode_summary_html_entities(text)

    if "<" not in text:
        return f"<p>{html.escape(text)}</p>"

    soup = BeautifulSoup(text, "html.parser")
    for node in list(soup.find_all(True)):
        _normalize_tag(node)

    body_html = "".join(str(child) for child in soup.children).strip()
    if not body_html:
        plain = soup.get_text(" ", strip=True)
        return f"<p>{html.escape(plain)}</p>" if plain else ""

    if not _has_block_element(body_html):
        return f"<p>{body_html}</p>"
    return body_html


def summary_html_to_plain_text(summary_html: str) -> str:
    """
    Extract plain text from summary HTML for clipboard ``text/plain`` payloads.

    Args:
        summary_html: HTML string (typically already normalized).

    Returns:
        Plain text with paragraph breaks preserved as newlines.
    """
    text = (summary_html or "").strip()
    if not text:
        return ""
    if "<" not in text:
        return text

    soup = BeautifulSoup(text, "html.parser")
    paragraphs: list[str] = []
    for element in soup.find_all(["p", "h1", "h2", "h3", "blockquote", "li"]):
        block_text = _block_plain_text(element)
        if block_text:
            paragraphs.append(block_text)
    if paragraphs:
        return "\n\n".join(paragraphs)
    return soup.get_text(" ", strip=True)


def _block_plain_text(element: Tag) -> str:
    """Return readable plain text for one block element."""
    text = re.sub(r"\s+", " ", element.get_text(separator=" ", strip=True)).strip()
    return re.sub(r" ([,.;:!?])", r"\1", text)


def _looks_like_escaped_html(text: str) -> bool:
    """Return True when angle brackets appear only as HTML entities."""
    return "&lt;" in text and "<" not in text


def _normalize_tag(node: Tag) -> None:
    """Rewrite or unwrap a tag to the DataLumos-safe subset."""
    name = node.name.lower() if node.name else ""
    if name in {"html", "head", "body"}:
        node.unwrap()
        return

    if name == "div":
        node.name = "p"
        name = "p"

    if name not in _ALLOWED_TAGS:
        node.unwrap()
        return

    allowed_attrs = {"href"} if name == "a" else set()
    for attr in list(node.attrs):
        if attr not in allowed_attrs:
            del node.attrs[attr]

    if name == "a":
        href = str(node.get("href") or "").strip()
        if not href:
            node.unwrap()


def _has_block_element(html_text: str) -> bool:
    """Return True when normalized HTML already contains block-level tags."""
    soup = BeautifulSoup(html_text, "html.parser")
    return any(
        isinstance(node, Tag) and (node.name or "").lower() in _BLOCK_TAGS
        for node in soup.find_all(True)
    )
