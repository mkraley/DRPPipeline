"""
Section builders for ADC catalog HTML snapshots from Figshare API metadata.
"""

from __future__ import annotations

from typing import Any

from collectors.AdcCatalogHtmlFormat import (
    data_table,
    doi_url,
    escape_text,
    format_custom_value,
    humanize_relation,
    link_or_text,
    list_section,
    table_section,
)
from utils.file_utils import format_file_size


def page_header(source_url: str) -> str:
    """Return the archival snapshot banner."""
    safe_url = escape_text(source_url)
    return (
        '<p class="meta-note">Ag Data Commons catalog record (archival snapshot from '
        f'Figshare API). Portal URL: <a href="{safe_url}">{safe_url}</a></p>'
    )


def page_footer() -> str:
    """Return the generation footer."""
    return (
        '<p class="meta-note">Catalog snapshot generated from Figshare API metadata '
        "(see adc_metadata.json in the project folder).</p>"
    )


def authors_section(article: dict[str, Any]) -> str:
    """Format author names and ORCID identifiers when present."""
    authors = article.get("authors") or []
    items: list[str] = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        name = escape_text(author.get("full_name"))
        if not name:
            continue
        orcid = str(author.get("orcid_id") or "").strip()
        if orcid:
            orcid_url = orcid if orcid.startswith("http") else f"https://orcid.org/{orcid}"
            items.append(f"{name} (<a href=\"{escape_text(orcid_url)}\">ORCID</a>)")
        else:
            items.append(name)
    return list_section("Authors", items)


def record_metadata_section(article: dict[str, Any], source_url: str) -> str:
    """Render core bibliographic and access metadata."""
    rows = [
        ("Portal URL", link_or_text(source_url)),
        ("Public HTML URL", link_or_text(str(article.get("url_public_html") or ""))),
        ("Figshare URL", link_or_text(str(article.get("figshare_url") or ""))),
        ("DOI", link_or_text(doi_url(str(article.get("doi") or "")))),
        ("Handle", escape_text(article.get("handle"))),
        ("Resource DOI", link_or_text(doi_url(str(article.get("resource_doi") or "")))),
        ("Resource title", escape_text(article.get("resource_title"))),
        ("Item type", escape_text(article.get("defined_type_name"))),
        ("Status", escape_text(article.get("status"))),
        ("Version", escape_text(article.get("version"))),
        ("Published", escape_text(article.get("published_date"))),
        ("License", _license_name(article)),
        ("Citation", escape_text(article.get("citation"))),
    ]
    return table_section("Record metadata", rows)


def categories_section(article: dict[str, Any]) -> str:
    """Render subject category labels."""
    categories = article.get("categories") or []
    titles = [
        escape_text(category.get("title"))
        for category in categories
        if isinstance(category, dict) and category.get("title")
    ]
    return list_section("Categories", titles)


def keywords_section(article: dict[str, Any]) -> str:
    """Render keyword and tag lists from the article payload."""
    keyword_items = [
        escape_text(keyword)
        for keyword in (article.get("keywords") or [])
        if keyword
    ]
    tag_items = [
        escape_text(tag.get("name") if isinstance(tag, dict) else tag)
        for tag in (article.get("tags") or [])
        if tag
    ]
    parts: list[str] = []
    if keyword_items:
        parts.append(list_section("Keywords", keyword_items))
    if tag_items and tag_items != keyword_items:
        parts.append(list_section("Tags", tag_items))
    return "\n".join(parts)


def description_section(article: dict[str, Any]) -> str:
    """Embed the Figshare HTML description."""
    description = str(article.get("description") or "").strip()
    if not description:
        return ""
    return f'<h2>Description</h2><div class="description">{description}</div>'


def custom_fields_section(article: dict[str, Any]) -> str:
    """Render all ADC custom fields."""
    rows: list[tuple[str, str]] = []
    for field in article.get("custom_fields") or []:
        name = str(field.get("name") or "").strip()
        value = field.get("value")
        if not name or value in (None, "", []):
            continue
        rows.append((escape_text(name), format_custom_value(value)))
    return table_section("Ag Data Commons metadata", rows)


def funding_section(article: dict[str, Any]) -> str:
    """Render funding acknowledgements and grant details."""
    parts: list[str] = []
    funding_text = str(article.get("funding") or "").strip()
    if funding_text:
        parts.append(
            f"<h2>Funding</h2><p>{escape_text(funding_text)}</p>"
        )
    grants = article.get("funding_list") or []
    rows: list[list[str]] = []
    for grant in grants:
        if not isinstance(grant, dict):
            continue
        rows.append([
            escape_text(grant.get("grant_code")),
            escape_text(grant.get("funder_name")),
            escape_text(grant.get("title")),
            link_or_text(str(grant.get("url") or "")),
        ])
    table = data_table(
        "Funding grants",
        ["Grant code", "Funder", "Title", "Link"],
        rows,
    )
    if table:
        parts.append(table)
    return "\n".join(parts)


def related_materials_section(article: dict[str, Any]) -> str:
    """Render related publications and linked datasets."""
    materials = article.get("related_materials") or []
    rows: list[list[str]] = []
    for material in materials:
        if not isinstance(material, dict):
            continue
        relation = humanize_relation(str(material.get("relation") or ""))
        identifier_type = escape_text(material.get("identifier_type"))
        identifier = escape_text(material.get("identifier"))
        title = escape_text(material.get("title"))
        link = link_or_text(str(material.get("link") or doi_url(identifier)))
        label = title or identifier
        rows.append([relation, identifier_type, label, link])
    return data_table(
        "Related materials",
        ["Relation", "Type", "Title / identifier", "Link"],
        rows,
    )


def references_section(article: dict[str, Any]) -> str:
    """Render bibliographic reference links."""
    references = article.get("references") or []
    items = [link_or_text(str(reference)) for reference in references if reference]
    return list_section("References", items)


def history_section(article: dict[str, Any]) -> str:
    """Render version and timeline history."""
    timeline = article.get("timeline") or {}
    rows = [
        ("Version", escape_text(article.get("version"))),
        ("Created", escape_text(article.get("created_date"))),
        ("Modified", escape_text(article.get("modified_date"))),
        ("Published", escape_text(article.get("published_date"))),
        ("Posted", escape_text(timeline.get("posted"))),
        ("First online", escape_text(timeline.get("firstOnline"))),
    ]
    return table_section("History", rows)


def files_section(article: dict[str, Any]) -> str:
    """Render the downloadable file inventory."""
    files = article.get("files") or []
    if not files:
        return "<h2>Files</h2><p>No files listed.</p>"
    rows: list[list[str]] = []
    for file_obj in files:
        if not isinstance(file_obj, dict):
            continue
        name = escape_text(file_obj.get("name") or "file")
        size = escape_text(format_file_size(int(file_obj.get("size") or 0)))
        mimetype = escape_text(file_obj.get("mimetype"))
        md5 = escape_text(file_obj.get("supplied_md5") or file_obj.get("computed_md5"))
        download = link_or_text(str(file_obj.get("download_url") or ""))
        rows.append([name, size, mimetype, md5, download])
    return data_table(
        "Files",
        ["Name", "Size", "Type", "MD5", "Download URL"],
        rows,
    )


def _license_name(article: dict[str, Any]) -> str:
    """Extract the license display name from the article payload."""
    license_obj = article.get("license")
    if isinstance(license_obj, dict):
        return escape_text(license_obj.get("name"))
    return ""
