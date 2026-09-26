"""Tests for mixed free-form + ICPSR collection keyword composition."""

from pathlib import Path

import pytest

from utils.CollectionKeywordGenerator import CollectionKeywordGenerator
from utils.IcpsrSubjectThesaurus import IcpsrSubjectThesaurus
from utils.SubjectKeywordGenerator import SubjectKeywordGenerator

THESAURUS_PATH = Path(__file__).resolve().parents[2] / "data" / "icpsr_subject_thesaurus.json"


@pytest.fixture(scope="module")
def generator() -> CollectionKeywordGenerator:
    subject = SubjectKeywordGenerator(IcpsrSubjectThesaurus.load(THESAURUS_PATH))
    return CollectionKeywordGenerator(subject)


class TestCollectionKeywordGenerator:
    def test_compose_puts_free_terms_before_icpsr_and_units(
        self, generator: CollectionKeywordGenerator
    ) -> None:
        terms = generator.compose(
            title="Continuous Water Quality Monitoring",
            aboutness="Long-term water quality monitoring on a national river.",
            source_keywords="APHNdidthis, Continuous, Water quality",
            unit_names=["Big South Fork", "Obed"],
            icpsr_limit=3,
        )
        assert terms[0] == "water quality"
        assert "river monitoring" in terms
        assert "water pollution" in terms
        assert "environmental monitoring" in terms
        assert "Big South Fork" in terms and "Obed" in terms
        assert "national parks" not in terms
        assert "APHNdidthis" not in terms
        assert "Continuous" not in terms

    def test_mammal_inventory_keeps_specific_taxa(
        self, generator: CollectionKeywordGenerator
    ) -> None:
        terms = generator.compose(
            title="Appalachian Highlands Network Mammal Inventory 2003-2004",
            aboutness="Data package for mammal inventory.",
            source_keywords="Bats, Rodents, Anabat, Pitfall Traps, Tennessee",
            unit_names=["Big South Fork", "Blue Ridge", "Obed"],
        )
        assert "wildlife inventory" in terms
        assert "mammals" in terms
        assert "bats" in terms
        assert "rodents" in terms
        assert "wildlife" in terms
        assert "Anabat" not in terms
        assert "Pitfall Traps" not in terms

    def test_format_keywords_joins_with_commas(self, generator: CollectionKeywordGenerator) -> None:
        text = generator.format_keywords(
            title="Freshwater Mussel Monitoring",
            aboutness="Monitor freshwater mussels and species richness; reintroduction.",
            source_keywords="APHNdidthis, Freshwater mussels",
            unit_names=["Big South Fork", "Obed"],
        )
        assert "freshwater mussels" in text
        assert "species richness" in text
        assert "wildlife" in text
        assert "Big South Fork" in text
        assert "Obed" in text
        assert "APHNdidthis" not in text
