"""
Serialize and parse principal investigator records for Storage and upload.
"""

from __future__ import annotations

import json
import re
from typing import Any

_AFFILIATION_RE = re.compile(r"^(?P<name>.+?)\s*\((?P<affiliation>[^)]+)\)\s*$")
_NAME_TOKEN_RE = re.compile(r"^[A-Z][A-Za-z.'’-]*$")
_LEGAL_SUFFIXES = frozenset(
    {"inc", "llc", "lc", "llp", "lp", "pc", "pllc", "ltd", "co", "corp", "corporation", "company"}
)
_JOB_TITLES = frozenset(
    {
        "administrator",
        "adviser",
        "advisor",
        "agronomist",
        "analyst",
        "archaeologist",
        "biologist",
        "botanist",
        "chief",
        "consultant",
        "coordinator",
        "curator",
        "director",
        "ecologist",
        "forester",
        "geologist",
        "historian",
        "hydrologist",
        "intern",
        "liaison",
        "manager",
        "officer",
        "planner",
        "professor",
        "ranger",
        "scientist",
        "specialist",
        "superintendent",
        "supervisor",
        "technician",
    }
)
_ORG_HINT_RE = re.compile(
    r"(?i)\b("
    r"national park service|park service|inventory|monitoring|program|"
    r"network|university|department|office|institute|laboratory|lab|"
    r"center|service|agency|bureau|foundation|museum|society"
    r")\b"
)


def normalize_investigator(raw: dict[str, Any]) -> dict[str, str] | None:
    """
    Normalize one investigator dict to first_name, last_name, affiliation.

    Returns None when neither name nor affiliation is present.
    """
    first = str(raw.get("first_name") or raw.get("firstName") or "").strip()
    last = str(raw.get("last_name") or raw.get("primaryName") or raw.get("lastName") or "").strip()
    affiliation = str(raw.get("affiliation") or "").strip()
    if not first:
        parsed = _person_from_unstructured(affiliation or last)
        if parsed:
            return parsed
    if not first and not last and not affiliation:
        return None
    return {
        "first_name": first,
        "last_name": last,
        "affiliation": affiliation,
    }


def _named_investigators(people: list[dict[str, str]]) -> list[dict[str, str]]:
    """Drop leads that are organizations rather than named people."""
    return [
        person
        for person in people
        if person.get("first_name") and person.get("last_name")
    ]


def investigators_from_irma_contacts(contacts: list[dict[str, Any]]) -> list[dict[str, str]]:
    """
    Build investigator records from raw IRMA contact person dicts.

    Corporate contacts (``isCorporate``) become affiliation for following
    named people that lack their own affiliation. An organization with no
    named person is omitted.
    """
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    pending_affiliation = ""
    for item in contacts:
        if not isinstance(item, dict):
            continue
        if _irma_contact_is_corporate(item):
            text = _corporate_affiliation_text(item)
            parsed = _person_from_unstructured(text)
            if not parsed:
                pending_affiliation = text
                continue
            item = {
                "firstName": parsed["first_name"],
                "primaryName": parsed["last_name"],
                "affiliation": parsed["affiliation"],
            }
        person = normalize_investigator(item)
        if person is None:
            continue
        if not person["affiliation"] and pending_affiliation:
            person = {**person, "affiliation": pending_affiliation}
        key = (
            person["first_name"].lower(),
            person["last_name"].lower(),
            person["affiliation"].lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(person)
    if not out and pending_affiliation:
        alone = normalize_investigator({"affiliation": pending_affiliation})
        if alone and alone.get("first_name") and alone.get("last_name"):
            out.append(alone)
    return _named_investigators(out)


def coalesce_corporate_affiliations(people: list[dict[str, str]]) -> list[dict[str, str]]:
    """
    Merge org-only lead entries into affiliation on following named people.

    Handles stored rows where a corporate IRMA contact was saved as
    ``last_name`` with an empty ``first_name``.
    """
    out: list[dict[str, str]] = []
    pending_affiliation = ""
    for person in people:
        if _looks_like_organization_only(person):
            pending_affiliation = person["last_name"] or person["affiliation"]
            continue
        merged = dict(person)
        if not merged["affiliation"] and pending_affiliation:
            merged["affiliation"] = pending_affiliation
        out.append(merged)
    if not out and pending_affiliation:
        alone = normalize_investigator({"affiliation": pending_affiliation})
        if alone and alone.get("first_name") and alone.get("last_name"):
            out.append(alone)
    return _named_investigators(out)


def parse_display_person(text: str) -> dict[str, str] | None:
    """
    Parse ``First Last (Affiliation)`` display text into an investigator dict.

    Organization-only tokens (no parenthetical affiliation) are stored as
    ``last_name`` so ``coalesce_corporate_affiliations`` can attach them to
    following people. Otherwise the last whitespace-separated token is the
    last name and the remainder is the first name.
    """
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return None
    match = _AFFILIATION_RE.match(cleaned)
    if match:
        name = match.group("name").strip()
        affiliation = match.group("affiliation").strip()
    else:
        name = cleaned
        affiliation = ""
    if not name:
        return normalize_investigator({"affiliation": affiliation})
    if not affiliation and _text_looks_like_organization(name):
        return normalize_investigator({"last_name": name})
    parts = name.split()
    if len(parts) == 1:
        return normalize_investigator({"last_name": parts[0], "affiliation": affiliation})
    return normalize_investigator(
        {
            "first_name": " ".join(parts[:-1]),
            "last_name": parts[-1],
            "affiliation": affiliation,
        }
    )


def serialize_investigators(people: list[dict[str, str]]) -> str:
    """Encode investigator list as JSON text for the Storage column."""
    cleaned = _named_investigators(
        [person for person in (normalize_investigator(item) for item in people) if person]
    )
    if not cleaned:
        return ""
    return json.dumps(cleaned, ensure_ascii=False)


def deserialize_investigators(raw: str | None) -> list[dict[str, str]]:
    """Decode Storage JSON (or legacy display strings) into investigator dicts."""
    text = (raw or "").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, list):
            people = [
                person
                for person in (
                    normalize_investigator(item) for item in payload if isinstance(item, dict)
                )
                if person
            ]
            return _named_investigators(coalesce_corporate_affiliations(people))
    people: list[dict[str, str]] = []
    for part in re.split(r"\s*;\s*", text):
        person = parse_display_person(part)
        if person:
            people.append(person)
    return _named_investigators(coalesce_corporate_affiliations(people))


def _person_from_unstructured(text: str) -> dict[str, str] | None:
    """
    Parse a lead stored as one string into first name, last name, and affiliation.

    Accepts ``First Last (Affiliation)``, ``First Last, affiliation, role``,
    and a bare ``First Last``. Organization-only text returns None.
    """
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return None
    match = _AFFILIATION_RE.match(cleaned)
    if match:
        name = match.group("name").strip()
        affiliation = match.group("affiliation").strip()
        split = _split_person_name(name)
        if split:
            first, last = split
            return {"first_name": first, "last_name": last, "affiliation": affiliation}
    if "," in cleaned:
        left, right = cleaned.split(",", 1)
        left = left.strip()
        right = right.strip()
        split = _split_person_name(left)
        if split and right and not _starts_with_legal_suffix(right):
            first, last = split
            return {"first_name": first, "last_name": last, "affiliation": right}
    split = _split_person_name(cleaned)
    if not split:
        return None
    first, last = split
    return {"first_name": first, "last_name": last, "affiliation": ""}


def _split_person_name(name: str) -> tuple[str, str] | None:
    """Return (first, last) when ``name`` is two or three personal-name tokens."""
    cleaned = " ".join((name or "").split()).strip()
    if not cleaned or _text_looks_like_organization(cleaned):
        return None
    parts = cleaned.split()
    if len(parts) not in (2, 3):
        return None
    if not all(_NAME_TOKEN_RE.match(part) for part in parts):
        return None
    if any(_starts_with_legal_suffix(part) for part in parts):
        return None
    if any(part.casefold() in _JOB_TITLES for part in parts):
        return None
    return " ".join(parts[:-1]), parts[-1]


def _starts_with_legal_suffix(text: str) -> bool:
    """Return True when text begins with a company suffix such as LLC or Inc."""
    token = text.split(",", 1)[0].strip().replace(".", "").lower()
    return token in _LEGAL_SUFFIXES


def _irma_contact_is_corporate(item: dict[str, Any]) -> bool:
    """Return True when an IRMA contact is an organization, not a person."""
    if item.get("isCorporate") is True:
        return True
    first = str(item.get("firstName") or item.get("first_name") or "").strip()
    if first:
        return False
    last = str(item.get("primaryName") or item.get("last_name") or item.get("lastName") or "").strip()
    affiliation = str(item.get("affiliation") or "").strip()
    if affiliation and not last:
        return True
    return bool(last) and _text_looks_like_organization(last)


def _corporate_affiliation_text(item: dict[str, Any]) -> str:
    """Prefer explicit affiliation, else the corporate primary name."""
    affiliation = str(item.get("affiliation") or "").strip()
    if affiliation:
        return affiliation
    return str(item.get("primaryName") or item.get("last_name") or item.get("lastName") or "").strip()


def _looks_like_organization_only(person: dict[str, str]) -> bool:
    """Return True when a stored investigator row is an org, not a person."""
    if person.get("first_name"):
        return False
    last = person.get("last_name") or ""
    affiliation = person.get("affiliation") or ""
    if affiliation and not last:
        return True
    return bool(last) and not affiliation and _text_looks_like_organization(last)


def _text_looks_like_organization(text: str) -> bool:
    """Heuristic for institutional names used as lead affiliations."""
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    if "," in cleaned:
        return True
    if len(cleaned.split()) >= 4:
        return True
    return bool(_ORG_HINT_RE.search(cleaned))
