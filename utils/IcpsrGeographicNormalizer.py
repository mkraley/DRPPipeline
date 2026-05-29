"""
Map USFS FGDC geographic metadata to ICPSR Geographic Names Thesaurus terms.

Loads preferred terms from data/icpsr_geographic_thesaurus.json (see
scripts/build_icpsr_geographic_thesaurus.py).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from utils.Logger import Logger

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_THESAURUS_PATH = REPO_ROOT / "data" / "icpsr_geographic_thesaurus.json"

# Extent text that should produce no geographic coverage entry.
_SKIP_EXTENT_RE = re.compile(
    r"^\s*(global|worldwide|world-wide|international|earth|planet)\s*\.?\s*$",
    re.IGNORECASE,
)

# Extra aliases not always present on scraped term pages.
_EXTRA_ALIASES: dict[str, str] = {
    "usa": "United States",
    "u.s.a.": "United States",
    "u.s.": "United States",
    "america": "United States",
    "u.s. virgin islands": "Virgin Islands of the United States",
    "us virgin islands": "Virgin Islands of the United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "great britain": "United Kingdom",
    "england": "United Kingdom",
    "czech republic": "Czechoslovakia",
    "russia": "Russia",
    "ussr": "USSR",
    "conus": "United States",
    "conterminous united states": "United States",
    "conterminus united states": "United States",
    "coterminous united states": "United States",
    "coterminus united states": "United States",
    "united states of america": "United States",
}

# ICPSR country-level US terms treated as aliases; emit one canonical label.
_US_COUNTRY_CANONICAL = "United States"
_US_COUNTRY_TERMS = frozenset({"United States", "United States of America"})

# Bbox spans larger than this (degrees) are treated as national/regional, not site-level.
_LOCAL_BBOX_MAX_SPAN_DEG = 4.0

# US states and DC: approximate bounding boxes (decimal degrees).
_US_STATE_BBOX: dict[str, tuple[float, float, float, float]] = {
    "Alabama": (30.2, 35.0, -88.5, -84.9),
    "Alaska": (51.2, 71.5, -179.0, -129.0),
    "Arizona": (31.3, 37.0, -114.8, -109.0),
    "Arkansas": (33.0, 36.5, -94.6, -89.6),
    "California": (32.5, 42.0, -124.5, -114.1),
    "Colorado": (37.0, 41.0, -109.1, -102.0),
    "Connecticut": (40.9, 42.1, -73.7, -71.8),
    "Delaware": (38.4, 39.8, -75.8, -75.0),
    "District of Columbia": (38.8, 39.0, -77.1, -76.9),
    "Florida": (24.5, 31.0, -87.6, -80.0),
    "Georgia": (30.4, 35.0, -85.6, -80.8),
    "Hawaii": (18.9, 22.2, -160.3, -154.8),
    "Idaho": (42.0, 49.0, -117.2, -111.0),
    "Illinois": (37.0, 42.5, -91.5, -87.5),
    "Indiana": (37.8, 41.8, -88.1, -84.8),
    "Iowa": (40.4, 43.5, -96.6, -90.1),
    "Kansas": (37.0, 40.0, -102.1, -94.6),
    "Kentucky": (36.5, 39.2, -89.6, -81.9),
    "Louisiana": (29.0, 33.0, -94.0, -88.8),
    "Maine": (43.0, 47.5, -71.1, -66.9),
    "Maryland": (37.9, 39.7, -79.5, -75.0),
    "Massachusetts": (41.2, 42.9, -73.5, -69.9),
    "Michigan": (41.7, 48.2, -90.4, -82.4),
    "Minnesota": (43.5, 49.4, -97.2, -89.5),
    "Mississippi": (30.2, 35.0, -91.7, -88.1),
    "Missouri": (36.0, 40.6, -95.8, -89.1),
    "Montana": (44.4, 49.0, -116.1, -104.0),
    "Nebraska": (40.0, 43.0, -104.1, -95.3),
    "Nevada": (35.0, 42.0, -120.0, -114.0),
    "New Hampshire": (42.7, 45.3, -72.6, -70.6),
    "New Jersey": (38.9, 41.4, -75.6, -73.9),
    "New Mexico": (31.3, 37.0, -109.1, -103.0),
    "New York": (40.5, 45.0, -79.8, -71.9),
    "North Carolina": (33.8, 36.6, -84.3, -75.5),
    "North Dakota": (45.9, 49.0, -104.1, -96.6),
    "Ohio": (38.4, 42.0, -84.8, -80.5),
    "Oklahoma": (33.6, 37.0, -103.0, -94.4),
    "Oregon": (42.0, 46.3, -124.6, -116.5),
    "Pennsylvania": (39.7, 42.3, -80.5, -74.7),
    "Puerto Rico": (17.9, 18.5, -67.9, -65.2),
    "Rhode Island": (41.1, 42.0, -71.9, -71.1),
    "South Carolina": (32.0, 35.2, -83.4, -78.5),
    "South Dakota": (42.5, 45.9, -104.1, -96.4),
    "Tennessee": (35.0, 36.7, -90.3, -81.6),
    "Texas": (25.8, 36.5, -106.7, -93.5),
    "Utah": (37.0, 42.0, -114.1, -109.0),
    "Vermont": (42.7, 45.0, -73.4, -71.5),
    "Virginia": (36.5, 39.5, -83.7, -75.2),
    "Washington": (45.5, 49.0, -124.8, -116.9),
    "West Virginia": (37.2, 40.6, -82.6, -77.7),
    "Wisconsin": (42.5, 47.1, -92.9, -86.8),
    "Wyoming": (41.0, 45.0, -111.1, -104.0),
}

# Extent phrases mapped before free-text NER (pattern, preferred term, confidence, source).
_BRITISH_VIRGIN_ISLANDS_RE = re.compile(r"\bbritish\s+virgin\s+islands\b", re.IGNORECASE)
_VIRGIN_ISLANDS_RE = re.compile(r"(?<!british\s)virgin\s+islands\b", re.IGNORECASE)
_CONUS_RE = re.compile(
    r"\bconus\b|"
    r"contermin(?:ous|inus|us)\s+united\s+states|"
    r"cotermin(?:ous|inus|us)\s+united\s+states",
    re.IGNORECASE,
)

_EXTENT_PHRASE_RULES: tuple[tuple[re.Pattern[str], str, str, str], ...] = (
    (_BRITISH_VIRGIN_ISLANDS_RE, "British Virgin Islands", "high", "extent_phrase"),
    (_VIRGIN_ISLANDS_RE, "Virgin Islands of the United States", "high", "extent_phrase"),
    (_CONUS_RE, "United States", "high", "extent_phrase"),
)

# US territories in ICPSR treated like states for match-priority (stop city/park NER).
_US_TERRITORY_TERMS = frozenset({"Virgin Islands of the United States", "American Samoa", "Guam"})


@dataclass(frozen=True)
class GeographicMatch:
    """One ICPSR thesaurus term match."""

    term: str
    confidence: str  # high, medium, low
    source: str


@dataclass
class GeographicNormalizeResult:
    """Result of normalizing USFS geographic metadata."""

    geographic_coverage: str = ""
    warnings: list[str] = field(default_factory=list)
    matches: list[GeographicMatch] = field(default_factory=list)


class IcpsrGeographicThesaurus:
    """In-memory ICPSR geographic term index."""

    def __init__(self, terms: list[dict[str, Any]]) -> None:
        self.preferred_terms: set[str] = set()
        self.alias_to_preferred: dict[str, str] = {}
        for entry in terms:
            preferred = entry["preferred"].strip()
            if not preferred:
                continue
            self.preferred_terms.add(preferred)
            self.alias_to_preferred[preferred.lower()] = preferred
            for alias in entry.get("aliases") or []:
                alias = str(alias).strip()
                if alias:
                    self.alias_to_preferred[alias.lower()] = preferred
        for alias, preferred in _EXTRA_ALIASES.items():
            if preferred in self.preferred_terms:
                self.alias_to_preferred[alias.lower()] = preferred
        self._terms_by_length = sorted(self.preferred_terms, key=len, reverse=True)

    @classmethod
    def load(cls, path: Path | None = None) -> IcpsrGeographicThesaurus:
        path = path or DEFAULT_THESAURUS_PATH
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(data["terms"])

    def resolve(self, phrase: str) -> str | None:
        """Map a phrase to a preferred term, or None."""
        key = phrase.strip().lower()
        if not key:
            return None
        if key in self.alias_to_preferred:
            return self.alias_to_preferred[key]
        # Title-case attempt for state names
        titled = phrase.strip().title()
        if titled in self.preferred_terms:
            return titled
        return None

    def find_in_text(self, text: str) -> list[GeographicMatch]:
        """Find thesaurus terms mentioned in free text (longest match first)."""
        if not text:
            return []
        lowered = text.lower()
        found: list[GeographicMatch] = []
        seen: set[str] = set()
        for term in self._terms_by_length:
            pattern = re.compile(r"\b" + re.escape(term.lower()) + r"\b")
            if pattern.search(lowered):
                if term not in seen:
                    seen.add(term)
                    found.append(GeographicMatch(term, "medium", "text"))
        for alias, preferred in _EXTRA_ALIASES.items():
            if preferred not in self.preferred_terms:
                continue
            if alias in ("u.s.", "us"):
                pattern = re.compile(
                    r"\b" + re.escape(alias) + r"(?!\s*virgin\s+islands)\b",
                    re.IGNORECASE,
                )
            else:
                pattern = re.compile(r"\b" + re.escape(alias) + r"\b", re.IGNORECASE)
            if pattern.search(lowered) and preferred not in seen:
                seen.add(preferred)
                found.append(GeographicMatch(preferred, "medium", "text_alias"))
        return found


@lru_cache(maxsize=1)
def _thesaurus() -> IcpsrGeographicThesaurus:
    return IcpsrGeographicThesaurus.load()


def _bbox_center(bbox: dict[str, float]) -> tuple[float, float] | None:
    try:
        west = float(bbox["west"])
        east = float(bbox["east"])
        south = float(bbox["south"])
        north = float(bbox["north"])
    except (KeyError, TypeError, ValueError):
        return None
    return ((south + north) / 2.0, (west + east) / 2.0)


def _bbox_spans(bbox: dict[str, float]) -> tuple[float, float]:
    """Return (lat_span, lon_span) in decimal degrees."""
    try:
        west = float(bbox["west"])
        east = float(bbox["east"])
        south = float(bbox["south"])
        north = float(bbox["north"])
    except (KeyError, TypeError, ValueError):
        return 0.0, 0.0
    return abs(north - south), abs(east - west)


def _is_local_scale_bbox(bbox: dict[str, float]) -> bool:
    lat_span, lon_span = _bbox_spans(bbox)
    return (
        lat_span <= _LOCAL_BBOX_MAX_SPAN_DEG
        and lon_span <= _LOCAL_BBOX_MAX_SPAN_DEG
    )


def _canonicalize_us_country_term(term: str) -> str:
    if term in _US_COUNTRY_TERMS:
        return _US_COUNTRY_CANONICAL
    return term


def _is_us_country_term(term: str) -> bool:
    return term in _US_COUNTRY_TERMS


def _has_us_country_match(matches: list[GeographicMatch]) -> bool:
    return any(_is_us_country_term(m.term) for m in matches)


def _indicates_national_us_coverage(
    extent: str,
    place_keywords: list[str] | None,
    matches: list[GeographicMatch],
    thesaurus: IcpsrGeographicThesaurus,
) -> bool:
    if _has_us_country_match(matches):
        return True
    if extent and _CONUS_RE.search(extent):
        return True
    for kw in place_keywords or []:
        if _CONUS_RE.search(kw):
            return True
        if _resolve_place_keyword(kw, thesaurus) in _US_COUNTRY_TERMS:
            return True
    return False


def _state_from_bbox(lat: float, lon: float) -> str | None:
    for state, (lat_min, lat_max, lon_min, lon_max) in _US_STATE_BBOX.items():
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return state
    return None


def _should_skip_extent(description: str) -> bool:
    return bool(description and _SKIP_EXTENT_RE.match(description.strip()))


def _is_us_state_or_territory(term: str) -> bool:
    return term in _US_STATE_BBOX or term in _US_TERRITORY_TERMS


def _has_us_state_match(matches: list[GeographicMatch]) -> bool:
    return any(_is_us_state_or_territory(m.term) for m in matches)


def _apply_extent_phrase_rules(
    text: str,
    matches: list[GeographicMatch],
    seen: set[str],
) -> None:
    for pattern, term, confidence, source in _EXTENT_PHRASE_RULES:
        if pattern.search(text):
            _add_match(matches, seen, term, confidence, source)


def _resolve_place_keyword(kw: str, thesaurus: IcpsrGeographicThesaurus) -> str | None:
    """Map a FGDC place keyword to an ICPSR preferred term, if possible."""
    resolved = thesaurus.resolve(kw)
    if resolved:
        return resolved
    phrase_matches: list[GeographicMatch] = []
    phrase_seen: set[str] = set()
    _apply_extent_phrase_rules(kw, phrase_matches, phrase_seen)
    if phrase_matches:
        return phrase_matches[0].term
    return None


def _has_sufficient_geographic_match(matches: list[GeographicMatch]) -> bool:
    """True when coverage is anchored by a state, territory, or country-level term."""
    if not matches:
        return False
    if _has_us_state_match(matches):
        return True
    return _has_us_country_match(matches)


def _should_warn_unmatched_place_keyword(
    kw: str,
    matches: list[GeographicMatch],
    thesaurus: IcpsrGeographicThesaurus,
) -> bool:
    """Only warn about site/local keywords when we lack a state-level match."""
    if _has_sufficient_geographic_match(matches):
        return False
    if _resolve_place_keyword(kw, thesaurus):
        return False
    return True


def _add_match(
    matches: list[GeographicMatch],
    seen: set[str],
    term: str,
    confidence: str,
    source: str,
) -> None:
    if term in seen:
        return
    thesaurus = _thesaurus()
    if term not in thesaurus.preferred_terms:
        resolved = thesaurus.resolve(term)
        if not resolved:
            return
        term = resolved
    term = _canonicalize_us_country_term(term)
    if term in seen:
        return
    seen.add(term)
    matches.append(GeographicMatch(term, confidence, source))


def normalize_geographic_metadata(
    *,
    geographic_extent_description: str = "",
    place_keywords: list[str] | None = None,
    bounding_box: dict[str, float] | None = None,
    thesaurus: IcpsrGeographicThesaurus | None = None,
) -> GeographicNormalizeResult:
    """
    Normalize USFS geographic fields to ICPSR thesaurus terms.

    Returns semicolon-delimited ``geographic_coverage`` and any review warnings.
    """
    thesaurus = thesaurus or _thesaurus()
    result = GeographicNormalizeResult()
    extent = (geographic_extent_description or "").strip()

    if _should_skip_extent(extent):
        return result

    matches: list[GeographicMatch] = []
    seen: set[str] = set()
    unresolved_keywords: list[str] = []

    for raw_kw in place_keywords or []:
        kw = raw_kw.strip()
        if not kw:
            continue
        resolved = _resolve_place_keyword(kw, thesaurus)
        if resolved:
            _add_match(matches, seen, resolved, "high", "place_keyword")
        else:
            unresolved_keywords.append(kw)

    if extent:
        _apply_extent_phrase_rules(extent, matches, seen)

    if extent:
        for match in thesaurus.find_in_text(extent):
            if _has_us_state_match(matches) and not _is_us_state_or_territory(match.term):
                continue
            # Prefer place keywords for city/local names; text scan can hit author names.
            if not _is_us_state_or_territory(match.term):
                if not any(
                    match.term.lower() in (kw.lower()) or kw.lower() in match.term.lower()
                    for kw in (place_keywords or [])
                ):
                    result.warnings.append(
                        f"Low-confidence geographic match (text): {match.term}"
                    )
                    continue
            _add_match(matches, seen, match.term, match.confidence, match.source)

    bbox_dict = bounding_box or {}
    if bbox_dict:
        national_us = _indicates_national_us_coverage(
            extent, place_keywords, matches, thesaurus
        )
        local_bbox = _is_local_scale_bbox(bbox_dict)

        if national_us or not local_bbox:
            if not _has_us_country_match(matches):
                _add_match(
                    matches,
                    seen,
                    _US_COUNTRY_CANONICAL,
                    "high" if national_us else "medium",
                    "national_coverage" if national_us else "bounding_box",
                )
        else:
            center = _bbox_center(bbox_dict)
            if center:
                lat, lon = center
                state = _state_from_bbox(lat, lon)
                if state and not _has_us_country_match(matches):
                    _add_match(matches, seen, state, "medium", "bounding_box")
                elif (
                    18.0 <= lat <= 72.0
                    and -180.0 <= lon <= -66.0
                    and not _has_us_state_match(matches)
                    and not _has_us_country_match(matches)
                ):
                    _add_match(
                        matches,
                        seen,
                        _US_COUNTRY_CANONICAL,
                        "medium",
                        "bounding_box",
                    )

    for match in matches:
        if match.confidence == "low":
            result.warnings.append(
                f"Low-confidence geographic match ({match.source}): {match.term}"
            )

    if matches and not _has_us_state_match(matches) and not _has_us_country_match(matches):
        # Single foreign country — no warning. Multiple unmatched fragments only warned above.
        pass

    if _has_us_state_match(matches):
        matches = [m for m in matches if not _is_us_country_term(m.term)]

    for kw in unresolved_keywords:
        if _should_warn_unmatched_place_keyword(kw, matches, thesaurus):
            result.warnings.append(
                f"Geographic place keyword not in ICPSR thesaurus: {kw!r}"
            )

    ordered_terms = sorted({m.term for m in matches}, key=str.lower)
    result.matches = matches
    result.geographic_coverage = "; ".join(ordered_terms)
    return result


def format_geographic_coverage(terms: list[str]) -> str:
    """Join ICPSR terms for storage / upload."""
    return "; ".join(t.strip() for t in terms if t and t.strip())


def parse_geographic_coverage_field(value: str) -> list[str]:
    """Split semicolon-delimited geographic coverage for upload."""
    if not value or not value.strip():
        return []
    return [part.strip() for part in value.split(";") if part.strip()]


def _truncate_for_log(text: str, max_len: int = 200) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1] + "…"


def _format_matches_for_log(matches: list[GeographicMatch]) -> str:
    if not matches:
        return "(none)"
    parts = [f"{m.term} ({m.confidence}, {m.source})" for m in matches]
    return "; ".join(parts)


def log_geographic_normalization(
    result: GeographicNormalizeResult,
    *,
    geographic_extent_description: str = "",
    place_keywords: list[str] | None = None,
    bounding_box: dict[str, float] | None = None,
    context: str = "",
) -> None:
    """
    Log geographic normalization inputs, outputs, and per-term confidence.

    Each accepted match is logged with its confidence level and source
    (``place_keyword``, ``text``, ``bounding_box``, ``us_mention``, etc.).
    """
    prefix = f"Geographic coverage{f' {context}' if context else ''}:"
    extent = (geographic_extent_description or "").strip()
    kw = place_keywords or []
    bbox = bounding_box or {}

    if _should_skip_extent(extent):
        Logger.info("%s skipped ambiguous extent %r", prefix, extent)
        return

    Logger.info(
        "%s extent=%r place_keywords=%s bounding_box=%s -> %r",
        prefix,
        _truncate_for_log(extent) if extent else "",
        kw or [],
        bbox or {},
        result.geographic_coverage or "",
    )
    if result.matches:
        Logger.info("%s matches: %s", prefix, _format_matches_for_log(result.matches))
    if result.warnings:
        Logger.info("%s review warnings: %s", prefix, "; ".join(result.warnings))
