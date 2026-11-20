"""Parse the AirData pre-generated download page into one series per column."""

from __future__ import annotations

from html.parser import HTMLParser

from sourcing import AqsCellText as cells
from sourcing.AqsFile import AqsFile
from sourcing.AqsSeries import AqsSeries


class AqsPageParser(HTMLParser):
    """Turn the download page into column series, skipping 0 KB zips."""

    def __init__(self) -> None:
        """Initialize parser state."""
        super().__init__(convert_charrefs=True)
        self._clear()

    def parse_html(self, html: str) -> list[AqsSeries]:
        """
        Parse a download page into series in page order.

        Args:
            html: HTML of ``download_files.html``.

        Returns:
            One series per column that links to at least one zip.
        """
        self.reset()
        self._clear()
        self.feed(html)
        self.close()
        return self._series()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Track headings, tables, cells, and links."""
        href = cells.attr(attrs, "href")
        if tag == "h2":
            self._pending_zip = ""
            self._in_heading = True
            self._heading = []
        elif tag == "table":
            self._header_stack.append(self._headers)
            self._headers = []
        elif tag in {"td", "th"}:
            self._begin_cell(tag == "th")
        elif tag == "a":
            self._href = href
        elif tag == "br" and self._in_cell:
            self._cell_text.append(" ")

    def handle_endtag(self, tag: str) -> None:
        """Finish the element opened in ``handle_starttag``."""
        if tag == "h2":
            self._section = "".join(self._heading).strip()
            self._in_heading = False
        elif tag == "table":
            self._headers = self._header_stack.pop() if self._header_stack else []
        elif tag in {"td", "th"}:
            self._finish_cell()
        elif tag == "tr":
            self._finish_row()
        elif tag == "a":
            self._finish_anchor()

    def handle_data(self, data: str) -> None:
        """Collect heading text, cell text, and the size after a loose zip link."""
        if self._in_heading:
            self._heading.append(data)
        if self._in_cell:
            self._cell_text.append(data)
        self._capture_loose_size(data)

    def _clear(self) -> None:
        """Reset column state for a new document."""
        self._section = ""
        self._in_heading = False
        self._heading: list[str] = []
        self._headers: list[str] = []
        self._header_stack: list[list[str]] = []
        self._row: list[tuple[str, list[str], bool]] = []
        self._row_header = False
        self._in_cell = False
        self._cell_header = False
        self._cell_text: list[str] = []
        self._cell_hrefs: list[str] = []
        self._href = ""
        self._pending_zip = ""
        self._pending_text: list[str] = []
        self._columns: dict[tuple[str, str], dict[str, object]] = {}

    def _begin_cell(self, is_header: bool) -> None:
        """Start a table cell."""
        self._in_cell = True
        self._cell_header = is_header
        self._cell_text = []
        self._cell_hrefs = []

    def _finish_cell(self) -> None:
        """Append the open cell to the current row."""
        self._keep_open_anchor()
        text = "".join(self._cell_text)
        self._row.append((text, list(self._cell_hrefs), self._cell_header))
        if self._cell_header:
            self._row_header = True
        self._in_cell = False

    def _keep_open_anchor(self) -> None:
        """Keep a link whose end tag is missing when the cell closes."""
        if not self._href:
            return
        self._cell_hrefs.append(self._href)
        self._href = ""

    def _finish_anchor(self) -> None:
        """Record a link inside a cell, or hold a loose zip until its size."""
        href = self._href
        self._href = ""
        if not href:
            return
        if self._in_cell:
            self._cell_hrefs.append(href)
            return
        name = cells.zip_name(href)
        if name and self._section:
            self._pending_zip = name
            self._pending_text = []

    def _capture_loose_size(self, data: str) -> None:
        """Attach a size that follows a zip link outside a table."""
        if not self._pending_zip or self._in_cell:
            return
        self._pending_text.append(data)
        text = "".join(self._pending_text)
        if "KB" not in text.upper():
            return
        self._add_zip(self._section, "", self._pending_zip, text)
        self._pending_zip = ""
        self._pending_text = []

    def _finish_row(self) -> None:
        """Store a header row or distribute a data row across columns."""
        if self._row_header:
            labels = [text.strip() for text, _hrefs, _header in self._row]
            if labels and labels[0].lower() == "year":
                labels = labels[1:]
            self._headers = labels
        else:
            self._read_data_row()
        self._row = []
        self._row_header = False

    def _read_data_row(self) -> None:
        """Read zip links from the data cells in this row."""
        if len(self._row) < 2 or not self._section:
            return
        data_cells = self._row[1:]
        if not self._headers and len(data_cells) == 1:
            self._read_data_cell("", data_cells[0])
            return
        for header, cell in zip(self._headers, data_cells):
            self._read_data_cell(header, cell)

    def _read_data_cell(
        self,
        column: str,
        cell: tuple[str, list[str], bool],
    ) -> None:
        """Add zips and advisory PDFs from one table cell."""
        text, hrefs, _header = cell
        for href in hrefs:
            found_zip = cells.zip_name(href)
            found_pdf = cells.pdf_name(href)
            if found_zip:
                self._add_zip(self._section, column, found_zip, text)
            elif found_pdf:
                self._add_advisory(self._section, column, found_pdf)

    def _add_zip(self, section: str, column: str, filename: str, text: str) -> None:
        """Record a zip, or count it when the page lists it as 0 KB."""
        bucket = self._bucket(section, column)
        cells.remember_prefix(bucket, filename)
        if cells.is_explicit_zero(text):
            bucket["omitted"] = int(bucket["omitted"]) + 1
            return
        files = cells.file_list(bucket, "files")
        files.append(AqsFile(filename, cells.row_count(text), cells.size_kb(text), "data"))

    def _add_advisory(self, section: str, column: str, filename: str) -> None:
        """Record one advisory PDF on a column."""
        advisories = cells.file_list(self._bucket(section, column), "advisories")
        if any(item.filename == filename for item in advisories):
            return
        advisories.append(AqsFile(filename, 0, 0, "advisory"))

    def _bucket(self, section: str, column: str) -> dict[str, object]:
        """Return the accumulator for a section and column, creating it if needed."""
        key = (section, column.strip())
        bucket = self._columns.get(key)
        if bucket is None:
            bucket = {"files": [], "advisories": [], "prefixes": [], "omitted": 0}
            self._columns[key] = bucket
        return bucket

    def _series(self) -> list[AqsSeries]:
        """Build series from columns that contain at least one zip name."""
        built: list[AqsSeries] = []
        for (section, column), bucket in self._columns.items():
            series = cells.series_from_bucket(section, column, bucket)
            if series is not None:
                built.append(series)
        return built
