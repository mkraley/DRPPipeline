"""Tests for ICPSR geographic normalization."""

from pathlib import Path

import pytest

from utils.IcpsrGeographicNormalizer import (
    GeographicMatch,
    GeographicNormalizeResult,
    IcpsrGeographicThesaurus,
    log_geographic_normalization,
    normalize_geographic_metadata,
    parse_geographic_coverage_field,
)

THESAURUS_PATH = Path(__file__).resolve().parents[2] / "data" / "icpsr_geographic_thesaurus.json"


@pytest.fixture(scope="module")
def thesaurus() -> IcpsrGeographicThesaurus:
    if not THESAURUS_PATH.is_file():
        pytest.skip("Run scripts/build_icpsr_geographic_thesaurus.py first")
    return IcpsrGeographicThesaurus.load(THESAURUS_PATH)


class TestIcpsrGeographicNormalizer:
    def test_global_extent_produces_no_coverage(self, thesaurus: IcpsrGeographicThesaurus) -> None:
        result = normalize_geographic_metadata(
            geographic_extent_description="global",
            thesaurus=thesaurus,
        )
        assert result.geographic_coverage == ""
        assert result.warnings == []

    def test_minnesota_from_extent_text(self, thesaurus: IcpsrGeographicThesaurus) -> None:
        result = normalize_geographic_metadata(
            geographic_extent_description=(
                "The USDA Forest Service Marcell Experimental Forest (MEF) is an 890 "
                "hectare tract of land located 40 km north of Grand Rapids, Minnesota."
            ),
            thesaurus=thesaurus,
        )
        assert "Minnesota" in result.geographic_coverage
        assert "United States" not in result.geographic_coverage

    def test_multi_state_list_with_usa(self, thesaurus: IcpsrGeographicThesaurus) -> None:
        result = normalize_geographic_metadata(
            geographic_extent_description=(
                "covers the states of Illinois, Indiana, Iowa, Michigan, Minnesota, "
                "Missouri, and Wisconsin in the USA"
            ),
            thesaurus=thesaurus,
        )
        for state in ("Illinois", "Indiana", "Iowa", "Michigan", "Minnesota", "Missouri", "Wisconsin"):
            assert state in result.geographic_coverage
        assert "United States" not in result.geographic_coverage

    def test_puerto_rico_place_keyword_and_bbox(self, thesaurus: IcpsrGeographicThesaurus) -> None:
        result = normalize_geographic_metadata(
            geographic_extent_description=(
                "The study area includes Bisley Experimental Watersheds in the "
                "Luquillo Experimental Forest in northeastern Puerto Rico."
            ),
            place_keywords=["Puerto Rico", "Luquillo Experimental Forest"],
            bounding_box={
                "west": -65.75,
                "east": -65.741,
                "north": 18.322,
                "south": 18.307,
            },
            thesaurus=thesaurus,
        )
        assert "Puerto Rico" in result.geographic_coverage
        assert not any("Luquillo" in w for w in result.warnings)

    def test_oregon_from_extent(self, thesaurus: IcpsrGeographicThesaurus) -> None:
        result = normalize_geographic_metadata(
            geographic_extent_description=(
                "South Umpqua Experimental Forest is located in the Umpqua National Forest "
                "which is in the southwest Oregon Cascades."
            ),
            thesaurus=thesaurus,
        )
        assert result.geographic_coverage == "Oregon"

    def test_virgin_islands_extent_phrase(self, thesaurus: IcpsrGeographicThesaurus) -> None:
        result = normalize_geographic_metadata(
            geographic_extent_description=(
                "Study sites on St. Croix and St. Thomas in the U.S. Virgin Islands."
            ),
            thesaurus=thesaurus,
        )
        assert result.geographic_coverage == "Virgin Islands of the United States"

    def test_us_virgin_islands_place_keyword(self, thesaurus: IcpsrGeographicThesaurus) -> None:
        result = normalize_geographic_metadata(
            place_keywords=["U.S. Virgin Islands"],
            geographic_extent_description="Monitoring plots on St. John.",
            thesaurus=thesaurus,
        )
        assert result.geographic_coverage == "Virgin Islands of the United States"
        assert result.warnings == []

    def test_local_forest_keywords_suppressed_when_state_matched(
        self, thesaurus: IcpsrGeographicThesaurus
    ) -> None:
        result = normalize_geographic_metadata(
            geographic_extent_description="South Umpqua Experimental Forest, Oregon.",
            place_keywords=["Oregon", "South Umpqua Experimental Forest", "Umpqua National Forest"],
            thesaurus=thesaurus,
        )
        assert result.geographic_coverage == "Oregon"
        assert result.warnings == []

    def test_british_virgin_islands_not_us_virgin_islands(
        self, thesaurus: IcpsrGeographicThesaurus
    ) -> None:
        result = normalize_geographic_metadata(
            geographic_extent_description="Field work in the British Virgin Islands.",
            thesaurus=thesaurus,
        )
        assert "Virgin Islands of the United States" not in result.geographic_coverage
        assert "British Virgin Islands" in result.geographic_coverage

    def test_conus_maps_to_united_states(self, thesaurus: IcpsrGeographicThesaurus) -> None:
        result = normalize_geographic_metadata(
            geographic_extent_description="Fuel moisture samples across CONUS.",
            thesaurus=thesaurus,
        )
        assert result.geographic_coverage == "United States"

    def test_coterminus_united_states(self, thesaurus: IcpsrGeographicThesaurus) -> None:
        result = normalize_geographic_metadata(
            geographic_extent_description="Coterminus United States forest inventory plots.",
            thesaurus=thesaurus,
        )
        assert result.geographic_coverage == "United States"

    def test_conus_keywords_not_kansas_from_national_bbox(
        self, thesaurus: IcpsrGeographicThesaurus
    ) -> None:
        result = normalize_geographic_metadata(
            place_keywords=["conterminous United States", "CONUS"],
            bounding_box={
                "west": -124.7,
                "east": -66.9,
                "north": 49.0,
                "south": 24.5,
            },
            thesaurus=thesaurus,
        )
        assert result.geographic_coverage == "United States"
        assert "Kansas" not in result.geographic_coverage

    def test_us_country_aliases_dedupe(self, thesaurus: IcpsrGeographicThesaurus) -> None:
        result = normalize_geographic_metadata(
            place_keywords=["CONUS"],
            geographic_extent_description="Coverage of the United States of America.",
            thesaurus=thesaurus,
        )
        assert result.geographic_coverage == "United States"

    def test_small_bbox_infers_state(self, thesaurus: IcpsrGeographicThesaurus) -> None:
        result = normalize_geographic_metadata(
            bounding_box={
                "west": -105.5,
                "east": -105.0,
                "north": 39.9,
                "south": 39.5,
            },
            thesaurus=thesaurus,
        )
        assert result.geographic_coverage == "Colorado"

    def test_us_state_match_skips_city_ner(self, thesaurus: IcpsrGeographicThesaurus) -> None:
        result = normalize_geographic_metadata(
            geographic_extent_description=(
                "Plots near Denver, Colorado in Rocky Mountain National Park."
            ),
            place_keywords=["Colorado"],
            thesaurus=thesaurus,
        )
        assert result.geographic_coverage == "Colorado"
        assert "Denver" not in result.geographic_coverage

    def test_parse_geographic_coverage_field(self) -> None:
        assert parse_geographic_coverage_field("Oregon; United States") == [
            "Oregon",
            "United States",
        ]

    def test_log_geographic_normalization_includes_confidence(
        self, thesaurus: IcpsrGeographicThesaurus
    ) -> None:
        from unittest.mock import patch

        from utils.Logger import Logger

        Logger.initialize(log_level="INFO", log_file=False)
        result = GeographicNormalizeResult(
            geographic_coverage="Oregon",
            matches=[GeographicMatch("Oregon", "medium", "text")],
        )
        with patch.object(Logger, "info") as mock_info:
            log_geographic_normalization(
                result,
                geographic_extent_description="southwest Oregon Cascades",
                context="DRPID 1",
            )
        combined = " ".join(
            str(c.args[0]) + " ".join(str(a) for a in c.args[1:])
            for c in mock_info.call_args_list
        )
        assert "DRPID 1" in combined
        assert "Oregon" in combined
        assert "medium" in combined
        assert "text" in combined
