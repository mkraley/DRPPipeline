"""Keywords copied from a title, summary, and downloaded table."""

from __future__ import annotations

import re
from functools import lru_cache

from interactive_collector.metadata_inference_tables import is_date_header, is_keyword_header
from interactive_collector.metadata_inference_places import is_state_header
from interactive_collector.metadata_inference_text import keywords_from_text
from interactive_collector.table_preview import TablePreview
from utils.IcpsrSubjectThesaurus import IcpsrSubjectThesaurus

_MAX_KEYWORDS = 12
_STOP = frozenset(
    {
        "a", "an", "the", "of", "and", "or", "for", "to", "in", "on", "by", "with",
        "from", "as", "at", "this", "that", "these", "those", "is", "are", "was", "were", "be",
        "its", "their", "each", "also", "into", "over", "after", "before", "during",
        "including", "include", "includes", "included", "available", "data", "dataset", "datasets",
        "file", "files", "summary", "list", "lists", "provided", "which", "not", "per", "via",
        "using", "used", "based", "see", "page", "pages", "updated", "update", "more", "than",
        "other", "such", "nrc", "information", "record", "records", "report", "reports",
        "number", "numbers", "date", "dates", "year", "years", "month", "months", "staff",
        "historical", "comprehensive", "demographic", "current", "related", "specific", "general",
        "biennial", "evaluated", "significant", "escalated", "name", "names", "value", "values",
        "status", "location", "locations", "note", "notes", "type", "types", "site", "sites",
        "link", "links", "description", "code", "codes", "unit", "units",
    }
)
_GENERIC = frozenset(
    {"type", "site", "name", "value", "status", "location", "date", "year", "note", "page", "link", "data"}
)
_EXAMPLE = re.compile(r"\be\.g\.,?\s*([^)]+)", re.IGNORECASE)
_BY_LIST = re.compile(r"\bby\s+([^.]{0,200})", re.IGNORECASE)
_PAREN = re.compile(r"\(([^)]{1,80})\)")
_CLAUSE = re.compile(
    r"\b(each|contains|contain|may|which|that|these|those|where|when)\b",
    re.IGNORECASE,
)
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9&'-]*")


def keywords_from_title_and_summary(title: str, summary: str) -> str:
    """Return keywords written in the title or summary."""
    labeled = keywords_from_text(f"{title}\n{summary}")
    terms = _split_keywords(labeled)
    _add_terms(terms, _title_phrases(title))
    _add_terms(terms, _example_terms(summary))
    _add_terms(terms, _parenthetical_terms(summary))
    _add_terms(terms, _thesaurus_terms(f"{title}\n{summary}"))
    _add_terms(terms, _listed_terms(summary))
    return "; ".join(_drop_shorter(terms)[:_MAX_KEYWORDS])


def keywords_from_table(preview: TablePreview) -> str:
    """Return column labels and short category values from one table."""
    terms: list[str] = []
    _add_terms(terms, [_header_phrase(header) for header in preview.headers])
    if not preview.truncated:
        for header, values in preview.categories.items():
            if _skip_header(header):
                continue
            _add_terms(terms, [value.lower() for value in values])
    return "; ".join(terms[:_MAX_KEYWORDS])


def _title_phrases(title: str) -> list[str]:
    """Return content-word phrases from each part of a title."""
    phrases: list[str] = []
    for part in re.split(r"[:;|]", title):
        words = _content_words(part)
        if not words:
            continue
        if len(words) == 1 and len(words[0]) < 5:
            continue
        if len(words) <= 6:
            phrases.append(" ".join(words))
        else:
            phrases.extend(word for word in words if len(word) >= 5)
    return phrases


def _example_terms(summary: str) -> list[str]:
    """Return short items from an 'e.g.' list."""
    found: list[str] = []
    for match in _EXAMPLE.finditer(summary):
        found.extend(_short_items(match.group(1)))
    return found


def _listed_terms(summary: str) -> list[str]:
    """Return short field names from a 'by' list."""
    found: list[str] = []
    for match in _BY_LIST.finditer(summary):
        found.extend(_short_items(match.group(1)))
    return found[:6]


def _parenthetical_terms(summary: str) -> list[str]:
    """Return acronyms and short alternative lists written in parentheses."""
    found: list[str] = []
    for match in _PAREN.finditer(summary):
        inner = match.group(1).strip()
        if re.fullmatch(r"[A-Z]{3,8}", inner):
            found.append(inner)
            continue
        if "," in inner or re.search(r"\bor\b", inner, re.IGNORECASE):
            found.extend(_short_items(inner))
    return found


def _short_items(text: str) -> list[str]:
    """Split a comma or 'or' list into cleaned phrases of a few words."""
    phrases: list[str] = []
    for item in re.split(r",|\bor\b|\band\b", text):
        raw = item.strip()
        if not raw or "(" in raw or len(raw.split()) > 3 or _CLAUSE.search(raw):
            continue
        words = _content_words(raw)
        if not words or len(words) > 3:
            continue
        if len(words) == 1 and (words[0] in _GENERIC or len(words[0]) < 5):
            continue
        phrases.append(" ".join(words))
    return phrases


def _header_phrase(header: str) -> str:
    """Return a column header with filler words removed."""
    if _skip_header(header):
        return ""
    words = _content_words(header)
    if not words or (len(words) == 1 and len(words[0]) < 5):
        return ""
    return " ".join(words[:4])


def _skip_header(header: str) -> bool:
    """True for date, state, and explicit keyword columns."""
    return is_date_header(header) or is_state_header(header) or is_keyword_header(header)


def _thesaurus_terms(text: str) -> list[str]:
    """Return ICPSR subject phrases that occur in the text."""
    lowered = text.lower()
    found = [term for term in _subject_phrases() if _contains_phrase(lowered, term)]
    found.sort(key=len, reverse=True)
    kept: list[str] = []
    for term in found:
        if any(_contains_phrase(longer, term) for longer in kept):
            continue
        kept.append(term)
    return kept


def _content_words(text: str) -> list[str]:
    """Return lowercase words that are not filler."""
    return [word.lower() for word in _WORD.findall(text) if word.lower() not in _STOP and len(word) > 2]


def _add_terms(terms: list[str], extra: list[str]) -> None:
    """Append terms that are not already present."""
    seen = {term.lower() for term in terms}
    for term in extra:
        text = term.strip()
        if not text or text.lower() in seen or len(terms) >= _MAX_KEYWORDS:
            continue
        seen.add(text.lower())
        terms.append(text)


def _drop_shorter(terms: list[str]) -> list[str]:
    """Drop a term when a longer selected term already contains it."""
    return [term for term in terms if not _contained_by_another(term, terms)]

def _contained_by_another(term: str, terms: list[str]) -> bool:
    """True when another selected term contains this one."""
    return any(term != other and _contains_phrase(other, term) for other in terms)


def _split_keywords(value: str) -> list[str]:
    """Split a semicolon keyword string."""
    return [part.strip() for part in value.split(";") if part.strip()]


def _contains_phrase(text: str, phrase: str) -> bool:
    """True when phrase occurs on word boundaries."""
    return re.search(rf"\b{re.escape(phrase.lower())}\b", text) is not None


@lru_cache(maxsize=1)
def _subject_phrases() -> tuple[str, ...]:
    """Load multi-word ICPSR subject labels once."""
    thesaurus = IcpsrSubjectThesaurus.load()
    phrases = [
        term for term in thesaurus.preferred_terms
        if " " in term and len(term) >= 4 and term.lower() not in _STOP
    ]
    return tuple(sorted(phrases, key=len, reverse=True))
