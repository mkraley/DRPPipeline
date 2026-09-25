"""Tests for the NPS subject-keyword trial script."""

from scripts.generate_nps_subject_keywords import keywords_for_record, parse_drpids
from utils.IcpsrSubjectThesaurus import IcpsrSubjectThesaurus
from utils.SubjectKeywordGenerator import SubjectKeywordGenerator


def test_parse_drpids_range_and_list() -> None:
    assert parse_drpids("1-3") == [1, 2, 3]
    assert parse_drpids("1, 5") == [1, 5]


def test_keywords_for_record_uses_product_titles() -> None:
    generator = SubjectKeywordGenerator(IcpsrSubjectThesaurus.load())
    generated = keywords_for_record(
        generator,
        title="Mammal inventory",
        abstract="Data package.",
        keywords="",
        products=["Bat and rodent survey in a national park"],
    )
    assert "wildlife" in generated
    assert "national parks" in generated
