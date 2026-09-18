"""
Map IRMA Project profiles to DataLumos sourcing fields and hierarchy rows.
"""

from __future__ import annotations

from typing import Any

from sourcing.NpsProfileGeography import profile_geographic_coverage
from sourcing.NpsProfileMetadata import (
    AGENCY,
    OFFICE,
    profile_keywords,
    profile_summary_html,
    profile_temporal_fields,
    profile_title,
)
from sourcing.NpsReferenceRules import (
    is_public_downloadable_product,
    product_public_file_count,
    profile_products,
    project_direct_public_file_count,
    reference_id_of,
    reference_profile_url,
)

__all__ = [
    "AGENCY",
    "OFFICE",
    "breadcrumb_text",
    "build_candidate_row",
    "profile_keywords",
    "profile_title",
    "public_products",
    "storage_updates_from_profile",
]


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


def storage_updates_from_profile(
    profile: dict[str, Any],
    *,
    filenames: list[str] | None = None,
) -> dict[str, Any]:
    """
    Build Storage fields from an IRMA Project landing page.

    Hierarchy breadcrumbs stay in ``collection_notes`` and are not included here.
    """
    fields: dict[str, Any] = {
        "agency": AGENCY,
        "office": OFFICE,
        "summary": profile_summary_html(profile),
        "keywords": profile_keywords(profile),
    }
    fields.update(profile_temporal_fields(profile, filenames=filenames))
    coverage = profile_geographic_coverage(profile)
    if coverage:
        fields["geographic_coverage"] = coverage
    return fields


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
    row: dict[str, Any] = {
        "url": reference_profile_url(project_id),
        "title": title,
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
    row.update(storage_updates_from_profile(profile))
    return row


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
