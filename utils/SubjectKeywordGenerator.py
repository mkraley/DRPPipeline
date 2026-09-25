"""
Choose ICPSR subject terms from source-document aboutness.

Terms are preferred labels from thesaurus 10001 only. Place names, agencies,
and form or genre words are left to other access points. The same source
concept always maps to the same term.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape

from utils.IcpsrSubjectThesaurus import IcpsrSubjectThesaurus

MAX_TERMS = 10

# Narrower term -> broader term. Keep the narrower label when both match.
_BROADER_OF: dict[str, str] = {
    "wildlife": "natural resources",
    "environmental degradation": "natural environment",
    "water pollution": "pollution",
    "national parks": "parks",
    "population decrease": "population",
}

# Specific topics first. Later terms are dropped first when the list exceeds MAX_TERMS.
_PRIORITY: tuple[str, ...] = (
    "endangered species",
    "wildlife",
    "water pollution",
    "environmental degradation",
    "law enforcement",
    "population decrease",
    "environmental monitoring",
    "conservation",
    "natural environment",
    "natural resources",
    "national parks",
)

# Direct hits that are too generic or the wrong sense for these source texts.
_BLOCKED_DIRECT: frozenset[str] = frozenset(
    {
        "community",
        "crime",
        "environment",
        "health",
        "management",
        "medicine",
        "parks",
        "policy",
        "pollution",
        "population",
        "quality of life",
        "recreation",
        "science",
    }
)


@dataclass(frozen=True)
class _ConceptRule:
    """A source phrase that always maps to one preferred term."""

    pattern: re.Pattern[str]
    term: str


_RULES: tuple[_ConceptRule, ...] = (
    _ConceptRule(re.compile(r"\bwater\s+quality\b|\bwater\s+pollution\b", re.I), "water pollution"),
    _ConceptRule(
        re.compile(r"\b(poach\w*|illegal(?:ly)?\s+harvest\w*|law enforcement)\b", re.I),
        "law enforcement",
    ),
    _ConceptRule(
        re.compile(r"\b(poach\w*|illegal(?:ly)?\s+harvest\w*|reintroduction|augmentation|conserv\w*)\b", re.I),
        "conservation",
    ),
    _ConceptRule(
        re.compile(r"\b(endangered species|threatened species|\bCITES\b)\b", re.I),
        "endangered species",
    ),
    _ConceptRule(
        re.compile(r"\b(mammals?|bats?|rodents?|mussels?|wildlife)\b", re.I),
        "wildlife",
    ),
    _ConceptRule(
        re.compile(r"\b(population\s+(decline|decrease)|declin\w+|decrease in)\b", re.I),
        "population decrease",
    ),
    _ConceptRule(
        re.compile(r"\b(poach\w*|illegal(?:ly)?\s+harvest\w*|environmental degradation|eliminat\w+)\b", re.I),
        "environmental degradation",
    ),
    _ConceptRule(
        re.compile(r"\b(plants?|flora|vegetation|water\s+quality|natural resources)\b", re.I),
        "natural resources",
    ),
    _ConceptRule(
        re.compile(r"\b(habitats?|ecosystems?|cobble(?:\s+bar)?|plant communit\w*)\b", re.I),
        "natural environment",
    ),
    _ConceptRule(
        re.compile(
            r"\b(national parks?|parkway|national river|wild and scenic)\b",
            re.I,
        ),
        "national parks",
    ),
)

_MONITORING_RE = re.compile(r"\b(monitor\w*|inventor(?:y|ies))\b", re.I)
_RESOURCE_RE = re.compile(
    r"\b(plants?|water|mussels?|mammals?|wildlife|habitats?|quality|communit\w*|species|rivers?)\b",
    re.I,
)
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


class SubjectKeywordGenerator:
    """Map title and aboutness text onto ICPSR subject terms."""

    def __init__(self, thesaurus: IcpsrSubjectThesaurus) -> None:
        """Require every rule target to be a preferred term."""
        self._thesaurus = thesaurus
        missing = [rule.term for rule in _RULES if not thesaurus.contains(rule.term)]
        if missing:
            raise ValueError(f"Thesaurus is missing rule terms: {', '.join(missing)}")
        self._terms_by_length = sorted(thesaurus.preferred_terms, key=len, reverse=True)

    def generate(self, title: str, aboutness: str) -> list[str]:
        """Return 0 to 10 preferred subject terms for one item."""
        text = f"{title}\n{aboutness}"
        chosen = self._from_rules(text)
        chosen.update(self._from_phrases(text))
        chosen = _drop_broader(chosen)
        return _cap(_sort_terms(chosen))

    def format_keywords(self, title: str, aboutness: str) -> str:
        """Return generated terms as a comma-separated string."""
        return ", ".join(self.generate(title, aboutness))

    def _from_rules(self, text: str) -> set[str]:
        """Apply the fixed concept-to-term rules."""
        chosen = {rule.term for rule in _RULES if rule.pattern.search(text)}
        if _MONITORING_RE.search(text) and _RESOURCE_RE.search(text):
            chosen.add("environmental monitoring")
        return {term for term in chosen if self._thesaurus.contains(term)}

    def _from_phrases(self, text: str) -> set[str]:
        """Add multi-word preferred terms that are repeated or appear in the title."""
        title, _, body = text.partition("\n")
        found: set[str] = set()
        for term in self._terms_by_length:
            if not _phrase_is_indexable(term):
                continue
            pattern = re.compile(r"\b" + re.escape(term) + r"\b", re.I)
            title_hit = pattern.search(title) is not None
            if title_hit or len(pattern.findall(body)) >= 2:
                found.add(term)
        return found


def _phrase_is_indexable(term: str) -> bool:
    """Skip one-word labels and generic terms that show up in passing."""
    if term.lower() in _BLOCKED_DIRECT or len(term) < 4:
        return False
    return " " in term


def aboutness_text(abstract: str, keywords: str, extra: str = "") -> str:
    """Join abstract, supplied keywords, and extra source text with tags removed."""
    raw = " ".join(part for part in (abstract, keywords, extra) if part)
    return _SPACE_RE.sub(" ", unescape(_TAG_RE.sub(" ", raw))).strip()


def _drop_broader(chosen: set[str]) -> set[str]:
    """Drop a broader term when its narrower term is already selected."""
    drop = {_BROADER_OF[term] for term in chosen if term in _BROADER_OF}
    return chosen - drop


def _sort_terms(chosen: set[str]) -> list[str]:
    """Order known topics by search value, then any other hits alphabetically."""
    rank = {term: index for index, term in enumerate(_PRIORITY)}
    return sorted(chosen, key=lambda term: (rank.get(term, len(_PRIORITY)), term.lower()))


def _cap(terms: list[str]) -> list[str]:
    """Keep at most MAX_TERMS, dropping the lowest-priority terms first."""
    if len(terms) <= MAX_TERMS:
        return terms
    return terms[:MAX_TERMS]
