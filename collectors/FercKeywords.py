"""
Keywords for FERC datasets.

Each dataset gets a few shared subject terms plus the form or program name
a reader would type. ICPSR preferred terms are used when the thesaurus has
one. Names such as Form 552, market-based rates, and hydropower are kept
even though they are not in the thesaurus, because DataLumos accepts them
and they are how these tables are found.
"""

from __future__ import annotations

# First matching title fragment wins, so narrower titles come first.
_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("page 3", ("Form 552", "natural gas", "price indexes")),
    ("form 552", ("Form 552", "natural gas", "natural gas industry", "prices")),
    ("oil assessment", ("oil industry", "petroleum industry", "regulation", "annual charges")),
    ("oil debit", ("oil industry", "petroleum industry", "regulation", "annual charges")),
    ("electric assessment", ("electric utilities", "electricity", "regulation", "annual charges")),
    ("electric debit", ("electric utilities", "electricity", "regulation", "annual charges")),
    ("gas assessment", ("natural gas industry", "natural gas utilities", "regulation", "annual charges")),
    ("gas debit", ("natural gas industry", "natural gas utilities", "regulation", "annual charges")),
    ("entities to gen", ("electric utilities", "power plants", "ownership")),
    ("gen assets", ("generation assets", "electric utilities", "power plants", "electricity")),
    ("market share", ("market-based rates", "electric utilities", "prices")),
    ("pivotal supplier", ("market-based rates", "electric utilities", "prices")),
    ("operating reserves", ("market-based rates", "electric utilities", "operating reserves")),
    ("mbr ", ("market-based rates", "electric utilities", "regulation")),
    ("entities to vertical", ("electric utilities", "natural gas", "ownership")),
    ("entities to ppa", ("electric utilities", "ownership", "energy industry")),
    ("entities to entities", ("electric utilities", "ownership", "energy industry")),
    ("information collection", ("government regulation", "regulatory agencies")),
    ("other federal agencies", ("hydropower", "licenses", "electric utilities", "annual charges")),
    ("administrative hydropower", ("hydropower", "licenses", "electric utilities", "annual charges")),
    ("company identifier", ("public utilities", "regulation", "company identifiers")),
    ("nepa", ("NEPA", "environmental impact", "infrastructure", "energy policy")),
    ("respondent information", ("Form 549D", "natural gas", "natural gas industry")),
    ("shipper and contract", ("Form 549D", "natural gas", "natural gas industry", "prices")),
    ("index of customer", ("Form 549B", "natural gas", "natural gas industry", "prices")),
    ("licensed marine", ("hydropower", "hydrokinetic", "licenses", "electricity")),
    ("conduit", ("hydropower", "licenses", "infrastructure")),
    ("active exemptions", ("hydropower", "licenses", "electric utilities")),
    ("relicensing", ("hydropower", "licenses", "electric utilities")),
    ("active licenses", ("hydropower", "licenses", "electric utilities")),
    ("topping-cycle", ("Form 556", "PURPA", "electric utilities", "cogeneration")),
    ("bottoming-cycle", ("Form 556", "PURPA", "electric utilities", "cogeneration")),
    ("affiliated small power", ("Form 556", "PURPA", "electric utilities", "ownership")),
    ("direct ownership", ("Form 556", "PURPA", "electric utilities", "ownership")),
    ("upstream", ("Form 556", "PURPA", "electric utilities", "ownership")),
    ("form 556", ("Form 556", "PURPA", "electric utilities", "energy production")),
    ("statement of income", ("Form 1", "public utilities", "electric utilities", "income")),
    ("plant in service", ("Form 1", "public utilities", "electric utilities", "power plants")),
    ("operation and maintenance", ("Form 1", "public utilities", "electric utilities")),
    ("form 1", ("Form 1", "public utilities", "electric utilities")),
    ("form 6", ("Form 6", "oil industry", "petroleum industry", "prices")),
)

# Terms a specialist searches that are not ICPSR preferred labels.
FREE_TEXT_TERMS = frozenset(
    {
        "Form 552",
        "Form 549B",
        "Form 549D",
        "Form 556",
        "Form 1",
        "Form 6",
        "PURPA",
        "NEPA",
        "market-based rates",
        "operating reserves",
        "hydropower",
        "hydrokinetic",
        "annual charges",
        "company identifiers",
        "cogeneration",
        "generation assets",
    }
)


def keywords_for_ferc(title: str, summary: str = "") -> str:
    """
    Return keywords for one FERC dataset.

    Args:
        title: Dataset title from the catalog.
        summary: Dataset description. Unused by the title rules; kept so callers
            can pass the project record without a second code path.

    Returns:
        Semicolon-separated keywords, or an empty string when the title is not
        one of the catalog families.
    """
    del summary
    heading = title.casefold()
    for needle, terms in _RULES:
        if needle in heading:
            return "; ".join(terms)
    return ""


def apply_ferc_keywords(fields: dict[str, str], title: str, summary: str = "") -> None:
    """Replace inferred keywords with the FERC catalog keywords when the title matches."""
    keywords = keywords_for_ferc(title, summary)
    if keywords:
        fields["keywords"] = keywords


def rule_terms() -> tuple[str, ...]:
    """Return every keyword assigned by a rule, in rule order."""
    terms: list[str] = []
    for _needle, assigned in _RULES:
        terms.extend(assigned)
    return tuple(terms)
