"""Tests for rowspan/colspan table expansion before markdownify."""

import unittest

from bs4 import BeautifulSoup
from markdownify import markdownify

from interactive_collector.html_table_expand import expand_tables_for_markdown


class TestHtmlTableExpand(unittest.TestCase):
    def test_rowspan_header_inserts_empty_cells_for_next_row(self) -> None:
        """EEOC-style: two rowspan=2 headers, then a row of FY cells only."""
        fy_cells = "".join(f"<th>FY{i}</th>" for i in range(5))
        data_cells = "".join(f"<td>{i}</td>" for i in range(5))
        html = f"""<html><body><table><thead>
<tr><th colspan="7">TITLE</th></tr>
<tr><th rowspan="2">No</th><th rowspan="2">Data</th><th colspan="5">Fiscal</th></tr>
<tr>{fy_cells}</tr>
</thead><tbody>
<tr><td>a</td><td>b</td>{data_cells}</tr>
</tbody></table></body></html>"""
        soup = BeautifulSoup(html, "html.parser")
        root = soup.body or soup
        ok, fail = expand_tables_for_markdown(root)
        self.assertEqual((ok, fail), (1, 0))
        md = markdownify(str(root), heading_style="ATX", bullets="-")
        table_lines = [ln for ln in md.splitlines() if ln.strip().startswith("|")]
        # Row with FY0 should start with two empty cells (No + Data columns)
        fy_line = next((ln for ln in table_lines if "FY0" in ln and "FY1" in ln), "")
        parts = [p.strip() for p in fy_line.split("|")]
        self.assertGreaterEqual(len(parts), 5, fy_line[:80])
        self.assertEqual(parts[1], "", fy_line[:80])
        self.assertEqual(parts[2], "", fy_line[:80])
        self.assertTrue(parts[3].startswith("FY"), parts[3])
