"""
Classify and reconcile Google Sheet inventory rows against Storage.

Used by ``scripts/reconcile_inventory_sheet.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence
from urllib.parse import urlparse, urlunparse


def normalize_url(url: str) -> str:
    u = (url or "").strip().lower()
    if not u:
        return ""
    parsed = urlparse(u)
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", parsed.query, ""))


def datalumos_project_id(url_or_id: str) -> str:
    s = (url_or_id or "").strip()
    m = re.search(r"/datalumos/project/(\d+)", s, re.I)
    if m:
        return m.group(1)
    if s.isdigit():
        return s
    return ""


def pick_sheet_col(row: Dict[str, str], *names: str) -> str:
    lower = {k.lower(): v for k, v in row.items()}
    for name in names:
        if name.lower() in lower:
            return lower[name.lower()]
    for key, val in row.items():
        if any(n.lower() in key.lower() for n in names):
            return val
    return ""


def norm_title(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").strip().lower())


def titles_match(db_title: str, sheet_title: str) -> bool:
    a, b = norm_title(db_title), norm_title(sheet_title)
    if not a and not b:
        return True
    if not a or not b:
        return False
    return a == b


@dataclass(frozen=True)
class ReconcileAction:
    drpid: int
    action: str  # ok | fix | append | skip
    reason: str
    db_url: str
    db_datalumos_id: str
    db_title: str
    sheet_url: str = ""
    sheet_datalumos_id: str = ""
    sheet_title: str = ""


def build_sheet_url_index(sheet_rows: Sequence[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    index: Dict[str, Dict[str, str]] = {}
    for row in sheet_rows:
        nu = normalize_url(pick_sheet_col(row, "URL"))
        if nu:
            index[nu] = row
    return index


def classify_reconcile_actions(
    db_rows: Sequence[Dict[str, object]],
    sheet_rows: Sequence[Dict[str, str]],
) -> List[ReconcileAction]:
    """
    Compare ``updated_inventory`` DB rows to sheet data using exact URL matching.

    Returns one action per DB row. ``ok`` rows need no sheet API call.
    """
    sheet_by_url = build_sheet_url_index(sheet_rows)
    actions: List[ReconcileAction] = []

    for row in db_rows:
        drpid = int(row["DRPID"])
        db_url = str(row.get("source_url") or "")
        db_dl = str(row.get("datalumos_id") or "").strip()
        db_title = str(row.get("title") or "")

        if not db_url.strip() or not db_dl:
            actions.append(
                ReconcileAction(
                    drpid,
                    "skip",
                    "missing source_url or datalumos_id",
                    db_url,
                    db_dl,
                    db_title,
                )
            )
            continue

        srow = sheet_by_url.get(normalize_url(db_url))
        if srow is None:
            actions.append(
                ReconcileAction(
                    drpid,
                    "append",
                    "exact URL not on sheet",
                    db_url,
                    db_dl,
                    db_title,
                )
            )
            continue

        sheet_url = pick_sheet_col(srow, "URL")
        sheet_dl_raw = pick_sheet_col(srow, "Download Location")
        sheet_dl = datalumos_project_id(sheet_dl_raw) or sheet_dl_raw
        sheet_title = pick_sheet_col(srow, "Title")

        if datalumos_project_id(sheet_dl_raw) == db_dl:
            actions.append(
                ReconcileAction(
                    drpid,
                    "ok",
                    "exact URL and datalumos_id match",
                    db_url,
                    db_dl,
                    db_title,
                    sheet_url,
                    sheet_dl,
                    sheet_title,
                )
            )
            continue

        actions.append(
            ReconcileAction(
                drpid,
                "fix",
                "exact URL on sheet but Download Location differs",
                db_url,
                db_dl,
                db_title,
                sheet_url,
                sheet_dl,
                sheet_title,
            )
        )

    return actions


def format_action_line(action: ReconcileAction, *, verbose: bool = False) -> str:
    lines = [f"DRPID {action.drpid:4d}  {action.action.upper():6s}  {action.reason}"]
    if verbose or action.action in ("fix", "append"):
        lines.append(f"  DB URL:   {action.db_url}")
        if action.action == "fix":
            lines.append(f"  Sheet URL: {action.sheet_url}")
        title = action.db_title[:80] or "(empty)"
        lines.append(f"  DB title: {title}")
        if action.action == "fix":
            st = action.sheet_title[:80] or "(empty)"
            tag = "MATCH" if titles_match(action.db_title, action.sheet_title) else "DIFFERS"
            lines.append(f"  Sheet title ({tag}): {st}")
        lines.append(f"  DB datalumos_id: {action.db_datalumos_id}")
        if action.action == "fix":
            lines.append(
                f"  Sheet datalumos_id: {action.sheet_datalumos_id}  ->  {action.db_datalumos_id}"
            )
    return "\n".join(lines)
