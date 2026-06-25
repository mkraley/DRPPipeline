"""Tests for temporal_utils."""

from __future__ import annotations

from utils.temporal_utils import (
    apply_temporal_inference,
    extract_dates_from_text,
    infer_time_end_from_filenames,
    merge_and_pair_time_updates,
    pair_time_fields,
)

WEATHER_FILENAMES = [
    "1989_15-min_weather_SWMRU_CPRL_1.xlsx",
    "2019_15-min_weather_SWMRU_CPRL.xlsx",
    "2023_15-min_weather_SWMRU_CPRL.xlsx",
    "README_Standard_Quality_Controlled_Research_Weather_Data_Bushland_TX.pdf",
]


class TestTemporalUtils:
    """Tests for temporal inference and pairing."""

    def test_extract_dates_from_text_year_prefix(self) -> None:
        """Leading year tokens in filenames are extracted."""
        dates = extract_dates_from_text("2019_15-min_weather_SWMRU_CPRL.xlsx")
        assert "2019" in dates

    def test_extract_dates_from_text_iso(self) -> None:
        """ISO-like dates with separators are extracted."""
        dates = extract_dates_from_text("data_2015-11-30_final.csv")
        assert "2015-11-30" in dates

    def test_infer_time_end_from_filenames(self) -> None:
        """Latest year across filenames is returned."""
        assert infer_time_end_from_filenames(WEATHER_FILENAMES) == "2023"

    def test_pair_time_fields_copies_start_to_end(self) -> None:
        """Missing end date is copied from start for DataLumos."""
        paired = pair_time_fields("2014-01-02", "")
        assert paired == {"time_start": "2014-01-02", "time_end": "2014-01-02"}

    def test_pair_time_fields_copies_end_to_start(self) -> None:
        """Missing start date is copied from end for DataLumos."""
        paired = pair_time_fields("", "2018")
        assert paired == {"time_start": "2018", "time_end": "2018"}

    def test_apply_temporal_inference_from_filenames(self) -> None:
        """Missing end date is inferred from filenames before pairing."""
        result = apply_temporal_inference(
            "1987-01-01",
            "",
            filenames=WEATHER_FILENAMES,
        )
        assert result["time_start"] == "1987-01-01"
        assert result["time_end"] == "2023"

    def test_apply_temporal_inference_falls_back_to_start(self) -> None:
        """When no filename dates exist, start is copied to end."""
        result = apply_temporal_inference("2014-01-02", "", filenames=[])
        assert result == {"time_start": "2014-01-02", "time_end": "2014-01-02"}

    def test_merge_and_pair_time_updates(self) -> None:
        """update_project merges current values then pairs them."""
        paired = merge_and_pair_time_updates(
            {"time_start": "2020", "time_end": ""},
            {"time_end": ""},
        )
        assert paired == {"time_start": "2020", "time_end": "2020"}
