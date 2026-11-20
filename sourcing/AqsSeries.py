"""One AirData download-page column, sourced as a single project."""

from __future__ import annotations

import re

from sourcing.AqsFile import AqsFile
from utils.datalumos_data_types import (
    DATA_TYPE_ADMINISTRATIVE,
    DATA_TYPE_AGGREGATE,
    DATA_TYPE_OBSERVATIONAL,
)

DOWNLOAD_PAGE_URL = "https://aqs.epa.gov/aqsweb/airdata/download_files.html"
FORMATS_FILENAME = "FileFormats.html"
INDEX_FILENAME = "file_list.csv"
AGENCY = "Environmental Protection Agency"
OFFICE = AGENCY
AQS_SUMMARY_NOTE = (
    "This data comes from EPA's Air Quality System (AQS). "
    "Data collection agencies report their data to EPA via this system and it "
    "calculates several types of aggregate (summary) data for EPA internal use. "
    "See FileFormats.html for details on the contents."
)

_OBSERVATIONAL_SECTIONS = frozenset(
    {"Hourly Data", "8-Hour Average Data", "Blanks Data"}
)
_YEAR_IN_NAME = re.compile(r"(?:19|20)\d{2}")
_PARAMETER_CODE = re.compile(r"\((\d+)\)")


class AqsSeries:
    """A table column of yearly zips, plus the extra files that go with it."""

    def __init__(
        self,
        series_id: str,
        section: str,
        column: str,
        files: tuple[AqsFile, ...] | list[AqsFile],
        omitted_empty: int = 0,
    ) -> None:
        """
        Store one download-page column.

        Args:
            series_id: Stable id used in the project URL fragment.
            section: Download-page heading, such as ``Daily Summary Data``.
            column: Column heading. Empty for the site listing and blanks.
            files: Non-empty data files and any advisory PDFs.
            omitted_empty: Count of zips listed as 0 KB and left out.
        """
        self.series_id = series_id
        self.section = section
        self.column = column
        self.files = tuple(files)
        self.omitted_empty = omitted_empty

    def title(self) -> str:
        """Return the DataLumos title for this column."""
        return f"Air Data {self._column_title()}"

    def source_url(self) -> str:
        """Return the unique project URL for this column."""
        return f"{DOWNLOAD_PAGE_URL}#{self.series_id}"

    def summary(self) -> str:
        """Return a short description of the files in this column."""
        return f"{self._description()} {AQS_SUMMARY_NOTE}"

    def collection_notes(self) -> str:
        """Return notes for extra files other than the format page."""
        names = [
            item.filename
            for item in self.packaged_files()
            if item.kind not in {"data", "format"}
        ]
        if not names:
            return ""
        if len(names) == 1:
            return f"Also save {names[0]}."
        listed = ", ".join(names[:-1]) + f" and {names[-1]}"
        return f"Also save {listed}."

    def packaged_files(self) -> tuple[AqsFile, ...]:
        """Return data files plus the format page, index, and advisories."""
        extras = [AqsFile(FORMATS_FILENAME, 0, 0, "format")]
        if self.series_id == "sites":
            extras.append(AqsFile(INDEX_FILENAME, 0, 0, "index"))
        advisories = [item for item in self.files if item.kind == "advisory"]
        data = [item for item in self.files if item.kind == "data"]
        return tuple(data + advisories + extras)

    def keywords(self) -> str:
        """Return semicolon-separated keywords, including a parameter code."""
        parts = ["air quality", "AQS", "AirData"]
        match = _PARAMETER_CODE.search(self.column)
        if match:
            parts.append(match.group(1))
        return "; ".join(parts)

    def data_type(self) -> str:
        """Return the DataLumos kind of data for this section."""
        if self.section.lower().startswith("site"):
            return DATA_TYPE_ADMINISTRATIVE
        if self.section in _OBSERVATIONAL_SECTIONS:
            return DATA_TYPE_OBSERVATIONAL
        return DATA_TYPE_AGGREGATE

    def metadata_fields(self) -> dict[str, str]:
        """Return the descriptive Storage columns for this column."""
        start, end = self._year_bounds()
        fields = {
            "title": self.title(),
            "summary": self.summary(),
            "agency": AGENCY,
            "office": OFFICE,
            "keywords": self.keywords(),
            "data_types": self.data_type(),
            "geographic_coverage": "United States",
            "extensions": "zip",
            "collection_notes": self.collection_notes(),
        }
        if start:
            fields["time_start"] = start
            fields["time_end"] = end
        return fields

    def storage_fields(self) -> dict[str, str]:
        """Return the Storage columns written when this series is first sourced."""
        fields = self.metadata_fields()
        fields["status"] = "sourced"
        return fields

    def _year_span_text(self) -> str:
        """Describe the yearly zip span."""
        start, end = self._year_bounds()
        count = sum(1 for item in self.files if item.kind == "data")
        if not start:
            return "No yearly data files are listed."
        if start == end:
            return f"One zip for {start}."
        return f"One zip per year from {start} through {end} ({count} files)."

    def _column_title(self) -> str:
        """Return the column title before the Air Data prefix."""
        column = self.column.strip()
        if not column:
            return self.section
        if column.lower().startswith(self.section.lower()):
            return column
        return f"{self.section} - {column}"

    def _description(self) -> str:
        """Return the column-specific summary before the shared AQS note."""
        if self.series_id == "sites":
            return (
                "Current Air Quality System site and monitor listings from the "
                "EPA AirData pre-generated download page, plus the file list "
                "for that page."
            )
        subject = self.column.strip() or self.section
        return (
            f"Pre-generated {self.section} files for {subject} from the EPA "
            f"AirData download page. {self._year_span_text()}{self._omitted_text()}"
        )

    def _omitted_text(self) -> str:
        """Describe zips left out because the page lists them as 0 KB."""
        if self.omitted_empty <= 0:
            return ""
        noun = "file" if self.omitted_empty == 1 else "files"
        return f" {self.omitted_empty} {noun} listed as 0 KB are omitted."

    def _year_bounds(self) -> tuple[str, str]:
        """Return the first and last year among data files."""
        years = [
            int(match.group(0))
            for item in self.files
            if item.kind == "data" and (match := _YEAR_IN_NAME.search(item.filename))
        ]
        if not years:
            return "", ""
        return str(min(years)), str(max(years))
