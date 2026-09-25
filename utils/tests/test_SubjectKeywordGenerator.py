"""Tests for ICPSR subject keyword generation."""

from pathlib import Path

import pytest

from utils.IcpsrSubjectThesaurus import IcpsrSubjectThesaurus
from utils.SubjectKeywordGenerator import SubjectKeywordGenerator, aboutness_text

THESAURUS_PATH = Path(__file__).resolve().parents[2] / "data" / "icpsr_subject_thesaurus.json"


@pytest.fixture(scope="module")
def generator() -> SubjectKeywordGenerator:
    return SubjectKeywordGenerator(IcpsrSubjectThesaurus.load(THESAURUS_PATH))


class TestSubjectKeywordGenerator:
    def test_water_quality_uses_water_pollution(self, generator: SubjectKeywordGenerator) -> None:
        terms = generator.generate(
            "Continuous Water Quality Monitoring",
            "Monitoring water quality in a national river.",
        )
        assert terms[0] == "water pollution" or "water pollution" in terms
        assert "environmental monitoring" in terms
        assert "national parks" in terms
        assert "wildlife" not in terms

    def test_poached_plants_skip_wildlife_and_use_law_enforcement(
        self, generator: SubjectKeywordGenerator
    ) -> None:
        terms = generator.generate(
            "Exploited Plants Monitoring",
            "Illegal harvesting of plants. Populations are declining along the parkway. "
            "Law enforcement may be deployed if plants are eliminated from habitats.",
        )
        assert "law enforcement" in terms
        assert "conservation" in terms
        assert "population decrease" in terms
        assert "environmental degradation" in terms
        assert "natural resources" in terms
        assert "wildlife" not in terms

    def test_cites_maps_to_endangered_species(self, generator: SubjectKeywordGenerator) -> None:
        terms = generator.generate("Rich coves", "Ginseng was included on the CITES list.")
        assert "endangered species" in terms

    def test_mammals_map_to_wildlife_not_natural_resources(
        self, generator: SubjectKeywordGenerator
    ) -> None:
        terms = generator.generate(
            "Mammal Inventory",
            "Inventory of bats and rodents in a national park.",
        )
        assert "wildlife" in terms
        assert "natural resources" not in terms
        assert "environmental monitoring" in terms

    def test_mussel_reintroduction_is_conservation(self, generator: SubjectKeywordGenerator) -> None:
        terms = generator.generate(
            "Freshwater Mussel Monitoring",
            "Monitoring mussels and assessing reintroduction in a wild and scenic river.",
        )
        assert "wildlife" in terms
        assert "conservation" in terms
        assert "population decrease" not in terms

    def test_population_decline_uses_preferred_term(self, generator: SubjectKeywordGenerator) -> None:
        terms = generator.generate("Plants", "A 30% decrease in plant abundance.")
        assert "population decrease" in terms
        assert "population decline" not in terms

    def test_terms_are_only_from_thesaurus(self, generator: SubjectKeywordGenerator) -> None:
        terms = generator.generate(
            "Galax monitoring on the Blue Ridge Parkway",
            "Poachers harvested plants. Water quality was not measured. Bats were absent.",
        )
        assert terms
        assert len(terms) <= 10
        for term in terms:
            assert generator._thesaurus.contains(term)

    def test_cobble_bar_is_natural_environment(self, generator: SubjectKeywordGenerator) -> None:
        terms = generator.generate(
            "Cobble Bar Community Monitoring",
            "Habitat quality of cobble bar communities along a national river.",
        )
        assert "natural environment" in terms
        assert "water pollution" not in terms

    def test_aboutness_text_strips_tags(self) -> None:
        text = aboutness_text("<p>Plants &amp; bats</p>", "galax", "brief")
        assert text == "Plants & bats galax brief"

    def test_empty_input_returns_no_terms(self, generator: SubjectKeywordGenerator) -> None:
        assert generator.generate("", "") == []

    def test_passing_mentions_are_not_indexed(self, generator: SubjectKeywordGenerator) -> None:
        terms = generator.generate(
            "Plant monitoring on the parkway",
            "The data provide evidence of education goals, products, and standards.",
        )
        assert "data" not in terms
        assert "evidence" not in terms
        assert "education" not in terms
        assert "natural resources" in terms
