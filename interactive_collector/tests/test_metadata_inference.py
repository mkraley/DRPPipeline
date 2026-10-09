"""Tests for inferring collector metadata from text and downloaded files."""

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from interactive_collector.app import app
from interactive_collector.metadata_inference import infer_project_metadata
from interactive_collector.metadata_inference_dates import excel_serial


def _xlsx(headers: list[str], rows: list[list[str]]) -> bytes:
    """Build a minimal xlsx workbook that uses inline strings."""
    sheet_rows = [_xlsx_row(1, headers)]
    for offset, row in enumerate(rows, start=2):
        sheet_rows.append(_xlsx_row(offset, row))
    sheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(sheet_rows)}</sheetData></worksheet>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return buffer.getvalue()


def _xlsx_row(number: int, values: list[str]) -> str:
    """Return one worksheet row of inline strings."""
    cells = []
    for index, value in enumerate(values):
        column = chr(ord("A") + index)
        cells.append(
            f'<c r="{column}{number}" t="inlineStr"><is><t>{value}</t></is></c>'
        )
    return f'<row r="{number}">{"".join(cells)}</row>'


class TestMetadataInference(unittest.TestCase):
    """Inference keeps only values stated in the text or the files."""

    def test_since_quarter_sets_start_only(self) -> None:
        """'since Q4 2000' is the start of that quarter, not an end date."""
        fields, _notes = infer_project_metadata(
            "Action matrix",
            "A summary of column data since Q4 2000.",
            None,
        )
        self.assertEqual(fields.get("time_start"), "2000-10-01")
        self.assertNotIn("time_end", fields)

    def test_united_states_phrase_sets_geography(self) -> None:
        """A stated United States coverage is kept."""
        fields, _notes = infer_project_metadata(
            "Reactor status",
            "Daily power reactor status for reactors in the United States.",
            None,
        )
        self.assertEqual(fields["geographic_coverage"], "United States")
        self.assertEqual(fields["data_types"], "Observational data")

    def test_agency_name_is_not_geography(self) -> None:
        """U.S. in an agency name is not geographic coverage."""
        fields, _notes = infer_project_metadata(
            "Board list",
            "Membership of the U.S. Nuclear Regulatory Commission CIO board.",
            None,
        )
        self.assertNotIn("geographic_coverage", fields)
        self.assertIn("board", fields["keywords"])

    def test_last_updated_and_past_month_are_not_dates(self) -> None:
        """A revision stamp and a rolling window are not a date range."""
        fields, _notes = infer_project_metadata(
            "Events",
            "Reports for the past month. Last Updated: 3/3/2025.",
            None,
        )
        self.assertNotIn("time_start", fields)
        self.assertNotIn("time_end", fields)

    def test_year_range_and_keywords_label(self) -> None:
        """A year span and an explicit keyword label are copied."""
        fields, _notes = infer_project_metadata(
            "Schedule 2025-2026",
            "Keywords: plume; ingestion.",
            None,
        )
        self.assertEqual(fields["time_start"], "2025")
        self.assertEqual(fields["time_end"], "2026")
        self.assertIn("plume", fields["keywords"])
        self.assertIn("ingestion", fields["keywords"])

    def test_docket_text_is_administrative(self) -> None:
        """Docket and violation language supports administrative records."""
        fields, _notes = infer_project_metadata(
            "Findings",
            "Findings and violations by docket since 2000.",
            None,
        )
        self.assertEqual(fields["time_start"], "2000")
        self.assertEqual(fields["data_types"], "Administrative records data")

    def test_csv_widens_dates_and_lists_states(self) -> None:
        """Year, month, state, and keyword columns in a downloaded file are used."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "plants.csv"
            path.write_text(
                "Year,Month,State,Keywords\n2020,3,TX,scram\n2024,11,CA,scram\n",
                encoding="utf-8-sig",
            )
            fields, notes = infer_project_metadata("Plants", "No dates here.", Path(folder))
        self.assertEqual(notes, [])
        self.assertEqual(fields["time_start"], "2020-03")
        self.assertEqual(fields["time_end"], "2024-11")
        self.assertEqual(fields["geographic_coverage"], "Texas; California")
        self.assertIn("scram", fields["keywords"])
        self.assertIn("plants", fields["keywords"])

    def test_summary_geography_wins_over_state_column(self) -> None:
        """United States in the summary is not replaced by a partial state list."""
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "plants.csv").write_text("State\nTX\n", encoding="utf-8-sig")
            fields, _notes = infer_project_metadata(
                "Reactors",
                "Commercial reactors in the United States.",
                Path(folder),
            )
        self.assertEqual(fields["geographic_coverage"], "United States")

    def test_xlsx_event_dates(self) -> None:
        """Dates in an xlsx date column become the range."""
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "events.xlsx").write_bytes(
                _xlsx(["Event Date"], [["1/15/2024"], ["3/2/2024"]])
            )
            fields, notes = infer_project_metadata("Events", "", Path(folder))
        self.assertEqual(notes, [])
        self.assertEqual(fields["time_start"], "2024-01-15")
        self.assertEqual(fields["time_end"], "2024-03-02")

    def test_excel_serial_date(self) -> None:
        """An Excel serial in the date range converts to a calendar date."""
        self.assertEqual(excel_serial("44927"), "2023-01-01")

    def test_data_dictionary_is_skipped(self) -> None:
        """A dictionary file is not treated as the dataset."""
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "hra-datadictionary.csv").write_text(
                "Keywords\nnot-a-keyword\n",
                encoding="utf-8-sig",
            )
            fields, _notes = infer_project_metadata("HRA", "A readme.", Path(folder))
        self.assertNotIn("not-a-keyword", fields.get("keywords", ""))

    def test_empty_project_adds_nothing(self) -> None:
        """No text and no files produce no fields."""
        fields, notes = infer_project_metadata("", "", None)
        self.assertEqual(fields, {})
        self.assertEqual(notes, [])

    def test_title_and_summary_supply_keywords(self) -> None:
        """Title phrases, summary examples, and stated subjects become keywords."""
        fields, _notes = infer_project_metadata(
            "Emergency Preparedness: NRC Biennial Evaluated Exercise Schedule",
            "Exercises at nuclear power reactors (e.g., plume, ingestion, partial).",
            None,
        )
        keywords = fields["keywords"]
        self.assertIn("emergency preparedness", keywords)
        self.assertIn("exercise schedule", keywords)
        self.assertIn("plume", keywords)
        self.assertIn("nuclear power", keywords)

    def test_spreadsheet_headers_and_categories(self) -> None:
        """Column headings and short category lists are keywords."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scrams.csv"
            path.write_text(
                "Docket Number,Scram Type\n05000220,Automatic\n05000247,Manual\n",
                encoding="utf-8-sig",
            )
            fields, _notes = infer_project_metadata("Scrams", "", Path(folder))
        keywords = fields["keywords"]
        self.assertIn("docket", keywords)
        self.assertIn("scram", keywords)
        self.assertIn("automatic", keywords)
        self.assertIn("manual", keywords)


class TestInferMetadataRoute(unittest.TestCase):
    """POST /api/infer-metadata reads the project and does not save."""

    def setUp(self) -> None:
        """Use the Flask test client."""
        self.client = app.test_client()

    def test_missing_project_returns_404(self) -> None:
        """An unknown DRPID is a 404."""
        with patch("interactive_collector.api_infer.get_project_by_drpid", return_value=None):
            response = self.client.post("/api/infer-metadata", json={"drpid": 4})
        self.assertEqual(response.status_code, 404)

    def test_route_returns_fields_from_summary(self) -> None:
        """The route returns fields found in the stored summary."""
        project = {
            "title": "Indicators",
            "summary": "Raw data for indicators in the United States since 2011.",
            "folder_path": "",
        }
        with patch("interactive_collector.api_infer.get_project_by_drpid", return_value=project):
            with patch("interactive_collector.api_infer.get_result_by_drpid", return_value={}):
                response = self.client.post("/api/infer-metadata", json={"drpid": 4})
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.data)
        self.assertEqual(payload["fields"]["time_start"], "2011")
        self.assertEqual(payload["fields"]["geographic_coverage"], "United States")
        self.assertIn("Observational data", payload["fields"]["data_types"])
