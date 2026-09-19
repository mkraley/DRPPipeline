"""
Count public IRMA Digital Files on a Project and nested public Products.
"""

from __future__ import annotations

from typing import Any

from sourcing.NpsReferenceRules import (
    as_reference_dicts,
    is_public_downloadable_product,
    product_public_file_count,
    project_direct_public_file_count,
    reference_id_of,
)


def descendant_reference_summaries(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Return Product/child summaries nested on a profile, first id only."""
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    nested = as_reference_dicts(profile.get("products")) + as_reference_dicts(
        profile.get("children")
    )
    for item in nested:
        ref_id = reference_id_of(item)
        if ref_id is not None:
            if ref_id in seen:
                continue
            seen.add(ref_id)
        rows.append(item)
    return rows


def recursive_public_file_count(profile: dict[str, Any]) -> int:
    """Sum public Digital Files on this reference and public descendant Products."""
    return _recursive_public_file_count(profile, seen=set(), is_root=True)


def _recursive_public_file_count(
    profile: dict[str, Any],
    seen: set[int],
    is_root: bool,
) -> int:
    """Walk one IRMA profile node, skipping cycles and restricted products."""
    ref_id = reference_id_of(profile)
    if ref_id is not None:
        if ref_id in seen:
            return 0
        seen.add(ref_id)
    if not is_root and not is_public_downloadable_product(profile):
        return 0
    total = _own_public_file_count(profile, is_root=is_root)
    for child in descendant_reference_summaries(profile):
        total += _recursive_public_file_count(child, seen, is_root=False)
    return total


def _own_public_file_count(profile: dict[str, Any], *, is_root: bool) -> int:
    """Count files on this node only (not descendants)."""
    listed = project_direct_public_file_count(profile)
    if listed:
        return listed
    if is_root:
        return 0
    return product_public_file_count(profile)
