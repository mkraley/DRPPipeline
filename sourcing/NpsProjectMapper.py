"""
Map IRMA Project profiles to DataLumos sourcing fields and hierarchy rows.
"""

from __future__ import annotations

import html
import re
from typing import Any

from sourcing.NpsReferenceRules import (
    is_public_downloadable_product,
    product_public_file_count,
    profile_products,
    project_direct_public_file_count,
    reference_id_of,
    reference_profile_url,
)

AGENCY = "National Park Service"
OFFICE = "Inventory and Monitoring Division"


def profile_title(profile: dict[str, Any]) -> str:
    """Return bibliography title, falling back to a top-level title."""
    bib = profile.get("bibliography") if isinstance(profile.get("bibliography"), dict) else {}
    return str(bib.get("title") or profile.get("title") or "").strip()


def profile_abstract(profile: dict[str, Any]) -> str:
    """Return a plain-text abstract from bibliography HTML when present."""
    bib = profile.get("bibliography") if isinstance(profile.get("bibliography"), dict) else {}
    return _plain_text(str(bib.get("abstract") or ""))


def profile_keywords(profile: dict[str, Any]) -> str:
    """Join unique keyword strings from an IRMA keywords payload."""
    names: list[str] = []
    for item in _keyword_items(profile.get("keywords")):
        if item and item not in names:
            names.append(item)
    return ", ".join(names)


def breadcrumb_text(
    *,
    collection_id: int,
    collection_title: str,
    program_id: int,
    program_title: str,
    project_id: int,
    project_title: str,
) -> str:
    """Build a Collection > Program > Project breadcrumb string."""
    return (
        f"Collection {collection_id}: {collection_title} > "
        f"Program {program_id}: {program_title} > "
        f"Project {project_id}: {project_title}"
    )


def html_paragraphs(*parts: str) -> str:
    """Wrap non-empty parts in ``<p>`` tags."""
    return "".join(f"<p>{html.escape(part)}</p>" for part in parts if part.strip())


def public_products(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Return Product summaries that have anonymously downloadable Digital Files."""
    return [
        product
        for product in profile_products(profile)
        if is_public_downloadable_product(product)
    ]


def project_public_file_total(profile: dict[str, Any]) -> int:
    """Sum public Digital Files on the Project and its public Products."""
    product_files = sum(product_public_file_count(product) for product in profile_products(profile))
    return project_direct_public_file_count(profile) + product_files


def build_candidate_row(
    *,
    collection_id: int,
    collection_title: str,
    program_id: int,
    program_title: str,
    profile: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Build a sourcing candidate for one IRMA Project.

    Returns:
        Candidate dict, or None when the Project has no public Digital Files.
    """
    project_id = reference_id_of(profile)
    title = profile_title(profile)
    if project_id is None or not title:
        return None
    public_files = project_public_file_total(profile)
    if public_files <= 0:
        return None
    products = [_product_row(product) for product in public_products(profile)]
    products = [row for row in products if row is not None]
    crumb = breadcrumb_text(
        collection_id=collection_id,
        collection_title=collection_title,
        program_id=program_id,
        program_title=program_title,
        project_id=project_id,
        project_title=title,
    )
    return {
        "url": reference_profile_url(project_id),
        "title": title,
        "agency": AGENCY,
        "office": OFFICE,
        "summary": html_paragraphs(crumb, profile_abstract(profile)),
        "keywords": profile_keywords(profile),
        "collection_notes": crumb,
        "record_id": str(project_id),
        "irma_project_id": project_id,
        "irma_program_id": program_id,
        "irma_collection_id": collection_id,
        "collection_title": collection_title,
        "program_title": program_title,
        "project_title": title,
        "breadcrumb": crumb,
        "public_file_count": public_files,
        "products": products,
    }


def _product_row(product: dict[str, Any]) -> dict[str, Any] | None:
    """Map a public Product summary to an nps_products row (without drpid)."""
    product_id = reference_id_of(product)
    title = str(product.get("title") or profile_title(product) or "").strip()
    if product_id is None or not title:
        return None
    return {
        "irma_product_id": product_id,
        "title": title,
        "reference_type": str(product.get("referenceType") or ""),
        "source_url": reference_profile_url(product_id),
        "visibility": str(product.get("visibility") or ""),
        "file_access": str(product.get("fileAccess") or ""),
        "public_file_count": product_public_file_count(product),
    }


def _plain_text(raw: str) -> str:
    """Strip tags and collapse whitespace from an IRMA abstract."""
    text = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _keyword_items(raw: Any) -> list[str]:
    """Flatten IRMA keyword objects into strings."""
    if isinstance(raw, dict):
        nested = raw.get("keyword") or raw.get("keywords")
        if nested is not None:
            return _keyword_items(nested)
        raw = list(raw.values())
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
        elif isinstance(item, dict):
            name = item.get("keyword") or item.get("text") or item.get("value")
            if name:
                names.append(str(name).strip())
    return names
