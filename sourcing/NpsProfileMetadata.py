"""
Extract IRMA Profile fields for DataLumos summary, dates, and geography.
"""

from __future__ import annotations

import html
import re
from typing import Any

from collectors.UsfsMetadataExtractor import normalize_temporal_date
from utils.temporal_utils import apply_temporal_inference

AGENCY = "Department of the Interior"
OFFICE = "National Park Service"
_CONTACT_LABELS = {
    "Lead(s)": "Leads",
    "Steward(s)": "Stewards",
    "Sponsor(s)": "Sponsors",
    "Author(s)": "Authors",
    "Creator(s)": "Creators",
    "Contact(s)": "Contacts",
}
_DOI_RE = re.compile(
    r"(?:https?://(?:dx\.)?doi\.org/)?(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)",
    re.IGNORECASE,
)


def bibliography(profile: dict[str, Any]) -> dict[str, Any]:
    """Return the bibliography object, or an empty dict."""
    raw = profile.get("bibliography")
    return raw if isinstance(raw, dict) else {}


def profile_title(profile: dict[str, Any]) -> str:
    """Return bibliography title, falling back to a top-level title."""
    return str(bibliography(profile).get("title") or profile.get("title") or "").strip()


def profile_abstract(profile: dict[str, Any]) -> str:
    """Return a plain-text abstract from bibliography HTML when present."""
    return _plain_text(str(bibliography(profile).get("abstract") or ""))


def profile_keywords(profile: dict[str, Any]) -> str:
    """Join unique keyword strings from an IRMA keywords payload."""
    names: list[str] = []
    for item in _keyword_items(profile.get("keywords")):
        if item and item not in names:
            names.append(item)
    return ", ".join(names)


def profile_publisher(profile: dict[str, Any]) -> str:
    """Return the publisher name from bibliography."""
    publisher = bibliography(profile).get("publisher")
    if isinstance(publisher, dict):
        return str(publisher.get("publisherName") or "").strip()
    return str(publisher or "").strip()


def irma_date(node: Any) -> str:
    """Normalize an IRMA issued/contentBegin/contentEnd date object."""
    if not isinstance(node, dict):
        return ""
    precision = str(node.get("precision") or "").upper()
    year = node.get("year")
    if precision == "YYYY" and year:
        return str(year)
    stamp = str(node.get("yyyymmdd") or node.get("YYYYMMDD") or "")
    if stamp:
        return normalize_temporal_date(stamp)
    if year:
        return str(year)
    bibliographic = str(node.get("bibliographic") or "").strip()
    return normalize_temporal_date(bibliographic) if bibliographic else ""


def profile_temporal_fields(
    profile: dict[str, Any],
    *,
    filenames: list[str] | None = None,
) -> dict[str, str]:
    """
    Build paired time_start/time_end from Project Start/End dates.

    Uses ``contentBegin`` / ``contentEnd``, falling back to ``issued``, then
    the shared filename inference and pairing helpers.
    """
    bib = bibliography(profile)
    start = irma_date(bib.get("contentBegin")) or irma_date(bib.get("issued"))
    end = irma_date(bib.get("contentEnd"))
    return apply_temporal_inference(start, end, filenames=filenames)


def contact_records(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Return contact roles and people lists from bibliography contacts."""
    records: list[dict[str, Any]] = []
    raw = bibliography(profile).get("contacts") or []
    if not isinstance(raw, list):
        return records
    for group in raw:
        if not isinstance(group, dict):
            continue
        raw_type = str(group.get("contactType") or "").strip()
        label = _CONTACT_LABELS.get(raw_type, raw_type.replace("(s)", "s") or "Contacts")
        people = [_format_person(item) for item in (group.get("contacts") or []) if isinstance(item, dict)]
        people = [name for name in people if name]
        if people:
            records.append({"role": label, "people": people})
    return records


def contact_groups(profile: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (label, formatted people) pairs from bibliography contacts."""
    return [(str(item["role"]), "; ".join(item["people"])) for item in contact_records(profile)]


def profile_notes(profile: dict[str, Any]) -> str:
    """Return plain-text Notes from the landing page bibliography."""
    return _plain_text(str(bibliography(profile).get("notes") or ""))


def profile_purpose(profile: dict[str, Any]) -> str:
    """Return plain-text Purpose from the landing page bibliography."""
    return _plain_text(str(bibliography(profile).get("purpose") or ""))


def profile_dois(profile: dict[str, Any]) -> list[str]:
    """Return unique DOIs from citation, notes, and dedicated identifier fields."""
    bib = bibliography(profile)
    chunks = [
        str(profile.get("citation") or ""),
        str(profile.get("doi") or profile.get("DOI") or ""),
        str(bib.get("doi") or bib.get("DOI") or ""),
        profile_notes(profile),
    ]
    found: list[str] = []
    for chunk in chunks:
        for match in _DOI_RE.finditer(chunk):
            doi = match.group(1).rstrip(").,;")
            if doi and doi not in found:
                found.append(doi)
    return found


def merge_doi_notes(existing: str, dois: list[str]) -> str:
    """Append ``DOI:`` lines to collection notes without duplicating them."""
    lines = [line for line in (existing or "").splitlines() if line.strip()]
    joined = "\n".join(lines)
    for doi in dois:
        note = f"DOI: {doi}"
        if note not in lines and doi not in joined:
            lines.append(note)
    return "\n".join(lines)


def profile_summary_html(profile: dict[str, Any]) -> str:
    """Build a DataLumos summary from abstract plus landing-page details."""
    chunks = [_paragraph(profile_abstract(profile))]
    citation = str(profile.get("citation") or "").strip()
    if citation:
        chunks.append(_labeled("Citation", citation))
    dois = profile_dois(profile)
    if dois:
        chunks.append(_labeled("DOI", "; ".join(dois)))
    for label, value in contact_groups(profile):
        chunks.append(_labeled(label, value))
    publisher = profile_publisher(profile)
    if publisher:
        chunks.append(_labeled("Publisher", publisher))
    notes = profile_notes(profile)
    if notes:
        chunks.append(_labeled("Notes", notes))
    purpose = profile_purpose(profile)
    if purpose:
        chunks.append(_labeled("Purpose", purpose))
    issued = irma_date(bibliography(profile).get("issued"))
    if issued:
        chunks.append(_labeled("Issued", issued))
    return "".join(chunk for chunk in chunks if chunk)


def _format_person(contact: dict[str, Any]) -> str:
    """Format one IRMA contact as 'First Last (Affiliation)'."""
    first = str(contact.get("firstName") or "").strip()
    last = str(contact.get("primaryName") or "").strip()
    name = " ".join(part for part in (first, last) if part)
    affiliation = str(contact.get("affiliation") or "").strip()
    if name and affiliation:
        return f"{name} ({affiliation})"
    return name or affiliation


def _plain_text(raw: str) -> str:
    """Strip tags and collapse whitespace."""
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


def _paragraph(text: str) -> str:
    """Wrap non-empty text in a paragraph."""
    return f"<p>{html.escape(text)}</p>" if text.strip() else ""


def _labeled(label: str, value: str) -> str:
    """Wrap a labeled landing-page field in a paragraph."""
    if not value.strip():
        return ""
    return f"<p><strong>{html.escape(label)}:</strong> {html.escape(value)}</p>"
