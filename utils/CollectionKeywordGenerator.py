"""
Compose collection keywords from aboutness, ICPSR terms, and place units.

Most terms are free-form searcher vocabulary. A few ICPSR Subject Thesaurus
labels are mixed in for DataLumos controlled-vocabulary coverage. Short NPS
unit names are appended when provided.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from utils.IcpsrSubjectThesaurus import IcpsrSubjectThesaurus
from utils.SubjectKeywordGenerator import SubjectKeywordGenerator, aboutness_text

MAX_UNCONSTRAINED = 8
MAX_ICPSR = 3


@dataclass(frozen=True)
class _FreeRule:
    """A source phrase that maps to one free-form keyword."""

    pattern: re.Pattern[str]
    term: str


_FREE_RULES: tuple[_FreeRule, ...] = (
    _FreeRule(re.compile(r"\bwater\s+quality\b", re.I), "water quality"),
    # Cobble-bar / habitat monitoring is not "river monitoring" by itself.
    _FreeRule(
        re.compile(
            r"\bwater\s+quality\b.{0,60}\b(river|stream)|\b(river|stream).{0,60}\bwater\s+quality|"
            r"\bdiscrete\s+water|\bcontinuous\s+water",
            re.I,
        ),
        "river monitoring",
    ),
    _FreeRule(re.compile(r"\b(poach\w*|illegal(?:ly)?\s+harvest\w*)\b", re.I), "plant poaching"),
    _FreeRule(re.compile(r"\b(floral|herbal)\s+markets?\b", re.I), "floral plants"),
    _FreeRule(
        re.compile(
            r"\b(medicinal|traditional medicinal|ginseng|black cohosh|bloodroot|cohosh)\b",
            re.I,
        ),
        "medicinal plants",
    ),
    _FreeRule(re.compile(r"\brich\s+coves?\b", re.I), "rich cove forests"),
    _FreeRule(re.compile(r"\bcobble(?:\s+bar)?s?\b", re.I), "cobble bars"),
    _FreeRule(re.compile(r"\b(riparian|river\s+scour)\b", re.I), "riparian vegetation"),
    _FreeRule(re.compile(r"\bCumberland\s+rosemary\b", re.I), "Cumberland rosemary"),
    _FreeRule(
        re.compile(r"\b(plant\s+communit\w*|cobble\s+bar\s+communit\w*)\b", re.I),
        "plant community monitoring",
    ),
    _FreeRule(
        re.compile(r"\b(exploited\s+plants?|plant(?:s)?\s+monitoring|galax)\b", re.I),
        "plant population monitoring",
    ),
    _FreeRule(
        re.compile(r"\bmammal(?:s)?\s+inventor|\binventor\w+\s+of\s+mammals?\b", re.I),
        "wildlife inventory",
    ),
    _FreeRule(re.compile(r"\b(freshwater\s+)?mussels?\b", re.I), "freshwater mussels"),
    _FreeRule(re.compile(r"\bspecies\s+richness\b", re.I), "species richness"),
    _FreeRule(
        re.compile(r"\bmussel\w*.{0,30}\bpopulations?\b|\bpopulations?\b.{0,30}\bmussel", re.I),
        "mussel populations",
    ),
    _FreeRule(re.compile(r"\bmammals?\b", re.I), "mammals"),
    _FreeRule(re.compile(r"\bbats?\b", re.I), "bats"),
    _FreeRule(re.compile(r"\brodents?\b", re.I), "rodents"),
)

_SPLIT_KW_RE = re.compile(r"[,;]+")
_SKIP_SOURCE_KW_RE = re.compile(
    r"didthis|trap|transect|anabat|echolocation|continuous|museum|"
    r"sherman|tomahawk|victor|pitfall|kentucky|tennessee|virginia|"
    r"north carolina|south carolina|exploited$",
    re.I,
)
# Parenthetical Latin names in titles, e.g. Galax (Galax urceolata).
_TITLE_BINOMIAL_RE = re.compile(r"\(([A-Z][a-z]+(?:\s+(?:spp\.|[a-z]+))?)\)")


class CollectionKeywordGenerator:
    """Build mixed free-form + ICPSR + unit keyword lists for collection."""

    def __init__(self, subject: SubjectKeywordGenerator | None = None) -> None:
        """Use a shared ICPSR generator, creating one when omitted."""
        self._subject = subject or _default_subject_generator()

    def generate_unconstrained(
        self,
        title: str,
        aboutness: str,
        source_keywords: str = "",
    ) -> list[str]:
        """Return free-form subject terms (majority of the keyword list)."""
        text = f"{title}\n{aboutness}"
        chosen: list[str] = []
        seen: set[str] = set()
        for rule in _FREE_RULES:
            if rule.pattern.search(text) or rule.pattern.search(source_keywords):
                _append_unique(chosen, seen, rule.term)
        for term in _source_keyword_candidates(source_keywords):
            _append_unique(chosen, seen, term)
        for term in _TITLE_BINOMIAL_RE.findall(title):
            _append_unique(chosen, seen, term)
        return chosen[:MAX_UNCONSTRAINED]

    def compose(
        self,
        *,
        title: str,
        aboutness: str,
        source_keywords: str = "",
        unit_names: list[str] | None = None,
        icpsr_limit: int = MAX_ICPSR,
    ) -> list[str]:
        """Combine unconstrained terms, a few ICPSR labels, and short unit names."""
        free = self.generate_unconstrained(title, aboutness, source_keywords)
        icpsr = self._subject.generate(title, aboutness)[:icpsr_limit]
        if unit_names:
            icpsr = [term for term in icpsr if term.lower() != "national parks"]
        result: list[str] = []
        seen: set[str] = set()
        for term in free + icpsr + list(unit_names or []):
            _append_unique(result, seen, term)
        return result

    def format_keywords(
        self,
        *,
        title: str,
        aboutness: str,
        source_keywords: str = "",
        unit_names: list[str] | None = None,
        icpsr_limit: int = MAX_ICPSR,
    ) -> str:
        """Return composed keywords as a comma-separated string."""
        return ", ".join(
            self.compose(
                title=title,
                aboutness=aboutness,
                source_keywords=source_keywords,
                unit_names=unit_names,
                icpsr_limit=icpsr_limit,
            )
        )


@lru_cache(maxsize=1)
def _default_subject_generator() -> SubjectKeywordGenerator:
    """Load the shared ICPSR subject generator once."""
    return SubjectKeywordGenerator(IcpsrSubjectThesaurus.load())


def _source_keyword_candidates(source_keywords: str) -> list[str]:
    """Keep useful source tags; drop methods, states, parks, and internal codes."""
    out: list[str] = []
    for part in _SPLIT_KW_RE.split(source_keywords or ""):
        term = part.strip()
        if len(term) < 3 or _SKIP_SOURCE_KW_RE.search(term):
            continue
        if term.lower() in {"water quality", "freshwater mussels"}:
            continue
        # Full park designations belong in the unit-name slot, not free keywords.
        if _looks_like_park_designation(term):
            continue
        out.append(term)
    return out


def _looks_like_park_designation(term: str) -> bool:
    """True when a source tag is a full NPS unit name with a designation suffix."""
    return bool(
        re.search(
            r"\b("
            r"National(?:\s+\w+){0,4}|"
            r"Wild(?:\s+and)?\s+Scenic|"
            r"Parkway|Network|Recreation(?:al)?\s+Area|"
            r"Scenic\s+River"
            r")\b",
            term,
            re.I,
        )
    )


def _append_unique(items: list[str], seen: set[str], term: str) -> None:
    """Append term when its lowercase form (or singular/plural twin) is new."""
    key = term.strip().lower()
    if not key:
        return
    variants = {key, key[:-1] if key.endswith("s") else key + "s"}
    if seen.intersection(variants):
        return
    seen.update(variants)
    items.append(term.strip())
