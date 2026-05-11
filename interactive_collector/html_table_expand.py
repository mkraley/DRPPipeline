"""
Expand HTML tables with rowspan/colspan into a simple grid before Markdown conversion.

BeautifulSoup + markdownify walk each ``<tr>``'s direct ``<td>``/``<th>`` children only.
Cells that only exist visually because of ``rowspan``/``colspan`` are absent from later
rows, so Markdown tables lose leading or interior columns. Normalizing to one cell per
grid position fixes that for any document, not a single site.

This runs on HTML **before** ``markdownify``; upstream ``markdownify`` is unchanged.
"""

from __future__ import annotations

from typing import Any, List, Optional, Union

from bs4 import BeautifulSoup, Tag

RootElement = Union[Tag, BeautifulSoup]

_COVERED = object()


def _owning_soup(tag: Tag) -> BeautifulSoup:
    p: Any = tag
    while p is not None:
        if isinstance(p, BeautifulSoup):
            return p
        p = p.parent
    raise RuntimeError("Tag has no BeautifulSoup ancestor")


def _table_trs_in_order(table: Tag) -> List[Tag]:
    """
    Return ``<tr>`` elements in document order.

    Includes ``<tr>`` that are direct children of ``<table>`` (before ``<thead>``),
    then rows inside ``thead`` / ``tbody`` / ``tfoot`` in tree order.
    """
    rows: List[Tag] = []
    for child in getattr(table, "children", ()) or ():
        if not getattr(child, "name", None):
            continue
        if child.name == "tr":
            rows.append(child)
        elif child.name in ("thead", "tbody", "tfoot"):
            rows.extend(child.find_all("tr", recursive=False))
    if rows:
        return rows
    for tr in table.find_all("tr", recursive=False):
        rows.append(tr)
    return rows


def _parse_span(val: Optional[str], default: int = 1, cap: int = 500) -> int:
    if not val:
        return default
    s = str(val).strip()
    if not s.isdigit():
        return default
    return max(1, min(cap, int(s)))


def _expand_single_table(table: Tag) -> None:
    """Mutate ``table`` in place: replace contents with a single ``<tbody>`` of flat rows."""
    rows = _table_trs_in_order(table)
    if not rows:
        return

    n_rows = len(rows)
    grid: List[List[Union[Tag, None, object]]] = [[] for _ in range(n_rows)]

    def _ensure_col(r: int, c: int) -> None:
        while len(grid[r]) <= c:
            grid[r].append(None)

    for r_idx, tr in enumerate(rows):
        cells = tr.find_all(["td", "th"], recursive=False)
        c_idx = 0
        for cell in cells:
            colspan = _parse_span(cell.get("colspan"))
            rowspan = _parse_span(cell.get("rowspan"))
            rowspan = min(rowspan, n_rows - r_idx)
            if rowspan < 1:
                rowspan = 1
            while True:
                _ensure_col(r_idx, c_idx)
                if grid[r_idx][c_idx] is None:
                    break
                c_idx += 1
            for dr in range(rowspan):
                for dc in range(colspan):
                    rr, cc = r_idx + dr, c_idx + dc
                    _ensure_col(rr, cc)
                    if dr == 0 and dc == 0:
                        grid[rr][cc] = cell
                    else:
                        grid[rr][cc] = _COVERED
            c_idx += colspan

    n_cols = max((len(row) for row in grid), default=0)
    for row in grid:
        while len(row) < n_cols:
            row.append(None)

    owner = _owning_soup(table)
    new_body = owner.new_tag("tbody")

    def _clone_cell_contents(new_cell: Tag, src_cell: Tag) -> None:
        """Copy inner nodes from ``src_cell`` into ``new_cell`` (no rowspan/colspan on copy)."""
        frag = BeautifulSoup(str(src_cell), "html.parser")
        src_inner = frag.find(["td", "th"])
        if not src_inner:
            return
        for ch in list(src_inner.contents):
            new_cell.append(ch)

    for r in range(len(grid)):
        new_tr = owner.new_tag("tr")
        row = grid[r]
        for c in range(n_cols):
            slot = row[c] if c < len(row) else None
            if slot is _COVERED:
                new_tr.append(owner.new_tag("td"))
                continue
            if isinstance(slot, Tag):
                name = "th" if slot.name == "th" else "td"
                new_cell = owner.new_tag(name)
                _clone_cell_contents(new_cell, slot)
                new_tr.append(new_cell)
            else:
                new_tr.append(owner.new_tag("td"))
        new_body.append(new_tr)

    for child in list(table.contents):
        if getattr(child, "name", None):
            child.extract()
    table.append(new_body)


def expand_tables_for_markdown(root: RootElement) -> tuple[int, int]:
    """Expand every ``<table>`` under ``root`` (mutates the tree in place).

    Returns ``(expanded_ok, expand_failed)`` for the save-markdown API response.
    """
    ok = 0
    failed = 0
    for tbl in list(root.find_all("table")):
        try:
            _expand_single_table(tbl)
            ok += 1
        except Exception:
            failed += 1
    return ok, failed
