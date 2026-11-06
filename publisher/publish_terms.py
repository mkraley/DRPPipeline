"""
Build the DataLumos publish request the review dialog already sends.

Captured from ``deposit.min.js`` build 20260910-150211. Publish Data POSTs the
``getTermsAndConditions`` object as JSON to ``/deposit/publish``. Storage
inventory is ``GET /deposit/viewStorage``.
"""

from __future__ import annotations

import copy
from typing import Any

from upload.deposit_page_request import DEPOSIT_SERVER, encode_query

# The license <select> posts the option value as a string. Public Domain Mark
# is 15 when the license list does not name it.
PUBLIC_DOMAIN_LICENSE_ID = "15"
PUBLISH_URL = f"{DEPOSIT_SERVER}/publish"

# Radio value from AccessibleQn. Required only when terms include accessibleQuestion.
ACCESSIBLE_ATTESTATION = (
    "Yes. I attest that I have made my deposited materials accessible to the "
    "best of my ability in accordance with "
    '<a href="https://www.icpsr.umich.edu/sites/icpsr/manage-data/'
    'Depositor-Guidelines-for-Sharing-Accessible-Study-Materials">'
    "ICPSR's Depositor Guidelines for Accessible Study Materials</a> to comply "
    'with <a href="https://www.w3.org/WAI/standards-guidelines/wcag/">'
    "Web Content Accessibility Guidelines (WCAG) 2.1 AA standards</a>."
)


def resource_path(workspace_id: str) -> str:
    """Return ``/datalumos/{id}`` for a numeric DataLumos project id."""
    if not str(workspace_id).isdigit():
        raise ValueError(f"DataLumos id must be numeric, got {workspace_id!r}")
    return f"/datalumos/{workspace_id}"


def view_storage_url(path: str) -> str:
    """URL for the Storage Status payload of one project."""
    return f"{DEPOSIT_SERVER}/viewStorage?path={encode_query(path)}"


def terms_url(path: str) -> str:
    """URL that loads the object Publish Data posts back."""
    return (
        f"{DEPOSIT_SERVER}/getTermsAndConditions?resourcePath={encode_query(path)}"
        "&type=project"
    )


def review_terms_url(path: str) -> str:
    """URL for the question text copied onto ``reviewTerms``."""
    return f"{DEPOSIT_SERVER}/getReviewTerms?resourcePath={encode_query(path)}"


def terms_attributes_url(path: str) -> str:
    """URL for which terms questions this project shows."""
    return f"{DEPOSIT_SERVER}/getTermsAttributes?path={encode_query(path)}"


def license_list_url(path: str) -> str:
    """URL for the license choices, including Public Domain Mark."""
    return f"{DEPOSIT_SERVER}/licenseList?path={encode_query(path)}"


def public_domain_license_id(licenses: object) -> str:
    """
    Return the Public Domain Mark id as the string the license select posts.

    Args:
        licenses: JSON from ``licenseList``.

    Raises:
        RuntimeError: When the list has no Public Domain Mark and no id 15.
    """
    if not isinstance(licenses, list):
        raise RuntimeError("licenseList did not return a list")
    named = _license_id_named(licenses, "public domain")
    if named is not None:
        return named
    if _has_license_id(licenses, PUBLIC_DOMAIN_LICENSE_ID):
        return PUBLIC_DOMAIN_LICENSE_ID
    raise RuntimeError("Public Domain Mark license was not in the license list")


def term_attribute_names(payload: object) -> set[str]:
    """Return ``attribute`` names nested in a ``getTermsAttributes`` payload."""
    names: set[str] = set()
    _collect_attribute_names(payload, names)
    return names


def apply_publish_answers(
    resource: object,
    review_terms: object,
    questions: set[str],
    license_id: str,
    version_title: str | None = None,
) -> dict[str, Any]:
    """
    Copy the terms dialog answers onto a ``getTermsAndConditions`` object.

    Disclosure is no, the data are not sensitive, download is public, there is
    no embargo, and the depositor agrees. ``version_title`` is set only for
    republish.

    Raises:
        RuntimeError: When ``resource`` is not an object.
    """
    if not isinstance(resource, dict):
        raise RuntimeError("getTermsAndConditions did not return an object")
    updated: dict[str, Any] = copy.deepcopy(resource)
    updated["disclosureRisk"] = "false"
    updated["sensitiveDataRisk"] = False
    updated["publicAccess"] = True
    updated["delayedDissemination"] = False
    updated["delayedDisseminationDateStr"] = None
    updated["delayedDisseminationDate"] = None
    updated["agreed"] = True
    updated["licenseId"] = license_id
    updated["reviewTerms"] = review_terms
    if "accessibleQuestion" in questions:
        updated["accessible"] = ACCESSIBLE_ATTESTATION
    if version_title:
        updated["versionTitle"] = version_title
    return updated


def _license_id_named(licenses: list[object], needle: str) -> str | None:
    """Return the id of the first license whose name contains ``needle``."""
    for item in licenses:
        if not isinstance(item, dict) or item.get("id") is None:
            continue
        name = str(item.get("name") or "").casefold()
        if needle not in name:
            continue
        return str(item["id"])
    return None


def _has_license_id(licenses: list[object], license_id: str) -> bool:
    """Return True when some license row uses ``license_id``."""
    for item in licenses:
        if isinstance(item, dict) and str(item.get("id")) == license_id:
            return True
    return False


def _collect_attribute_names(node: object, names: set[str]) -> None:
    """Add every string ``attribute`` field under ``node``."""
    if isinstance(node, dict):
        attribute = node.get("attribute")
        if isinstance(attribute, str) and attribute:
            names.add(attribute)
        for value in node.values():
            _collect_attribute_names(value, names)
        return
    if isinstance(node, list):
        for item in node:
            _collect_attribute_names(item, names)
