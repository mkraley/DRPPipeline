"""
Collect PDFs for the "Latest NHANES Data Releases" page.

This is a standalone utility script (not a pipeline module).

It loads the home page, finds the main-column sections for the requested
months (e.g. March / February / January 2026). Under each month it separates
**Data Release** and **Updated Data** into subfolders. Months with no
"Updated Data" links omit that subfolder.

Per link, the script opens the target **Data** page, names a subfolder from
the full ``<li>`` line on the Latest.aspx page, then saves a print-to-PDF of
the Data page. It then follows each link in the **in-page** bullet list (the
list that includes “Laboratory Variable List”), saving each target as a PDF
under that same subfolder (with names derived from the link text; methods /
manuals pages use a per-link subfolder for the table PDFs). The Laboratory
Variable List page uses the site **Print** control (``#print``) before
generating the PDF. Pages with a **Documentation** / **Document** column
also download those linked ``.pdf`` files into a **Documentation** subfolder.
On the Search **Data** page, under the in-page nav list, a table lists
**Data File Name**, **Doc File**, **Data File**, and **Date Published**; the
script creates a subfolder per row (named from Data File Name), then downloads
the Doc File and Data File into it. (Use ``--no-data-file-table`` to skip.)
If two output names collide, a numeric suffix is applied. Very long
filename stems are shortened by keeping a prefix and suffix (see
``_shorten_filename_stem``) so paths stay under typical Windows limits.

Run from repo root:
    python scripts/collect_cdc_nhanes_latest_pdfs.py ^
      --dest "C:\\Documents\\DataRescue\\CDCData\\DRP000001"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urljoin, urlparse

import requests  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright  # noqa: E402

from interactive_collector.pdf_utils import (  # noqa: E402
    page_title_or_h1,
    unique_pdf_basename,
)
from utils.Logger import Logger  # noqa: E402
from utils.file_utils import sanitize_filename  # noqa: E402


DEFAULT_HOME_URL = "https://wwwn.cdc.gov/nchs/nhanes/DataReleases/Latest.aspx"
DEFAULT_MONTHS = ["March 2026", "February 2026", "January 2026"]


@dataclass(frozen=True)
class ExtractedLink:
    month_label: str
    """Canonical month line, e.g. 'February 2026'."""

    category: str
    """'Data Release' or 'Updated Data'."""

    url: str
    anchor_text: str
    """Text of the link element only (for metadata)."""

    list_item_text: str
    """Full ``<li>`` text, including text after the link; used for folder names."""


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


# Windows: avoid MAX_PATH (260) failures on deep trees; cap each path component.
_STEM_MAX_LIST_FOLDER = 80
_STEM_MAX_RELATED_PDF = 100
_STEM_MAX_DOC_PDF = 64
_STEM_MAX_METHODS_SUBFOLDER = 64
_STEM_MAX_DATA_FILE_SUBFOLDER = 64


def _shorten_filename_stem(raw: str, max_stem: int) -> str:
    """
    Sanitize, then if still over ``max_stem`` characters keep the start and end
    with a short separator (Windows-safe path components).
    """
    s = sanitize_filename((raw or "").strip(), max_length=min(500, max(80, max_stem * 6)))
    if not s:
        s = "unnamed"
    if len(s) <= max_stem:
        return s
    sep = "___"
    budget = max_stem - len(sep)
    if budget < 12:
        return s[:max_stem]
    h = budget // 2
    t = budget - h
    return s[:h] + sep + s[-t:]


def _month_dir_name(month_label: str) -> str:
    # Make "March 2026" sort-friendly and stable on disk
    parts = month_label.strip().split()
    if len(parts) == 2 and parts[1].isdigit():
        month, year = parts[0], parts[1]
        return sanitize_filename(f"{year}-{month}", max_length=32)
    return sanitize_filename(month_label, max_length=40)


def _category_dir_name(category: str) -> str:
    return sanitize_filename(category.strip() or "section", max_length=50)


def _norm_anchor(text: str) -> str:
    return " ".join((text or "").split()).lower()


def _is_nhanes_datapage_href(href: str) -> bool:
    """
    True for NHANES Search ``DataPage.aspx`` links. Excludes share widgets (Facebook, etc.).
    """
    h = (href or "").strip()
    if not h or h.startswith("#") or h.lower().startswith("javascript:"):
        return False
    path = (urlparse(h).path or "").lower()
    return "datapage.aspx" in path


def _unique_sanitized_dirname(base: str, used: dict[str, int], parent: Path, *, max_len: int = 100) -> str:
    """
    Return a unique folder name under `parent` (no overwrite; suffix _1, _2, ...).
    Long names are shortened with the start and end preserved where possible.
    """
    safe = _shorten_filename_stem((base or "").strip(), max_len)
    safe = sanitize_filename(safe, max_length=max_len)
    if not safe:
        safe = "page"
    key = safe.lower()
    n = used.get(key, 0)
    while True:
        name = f"{safe}" if n == 0 else f"{safe}_{n}"
        if (parent / name).exists():
            n += 1
            continue
        used[key] = n + 1
        return name


def _extract_main_column_links(
    page: Page, base_url: str, month_labels: list[str]
) -> list[ExtractedLink]:
    """
    Extract Data Release / Updated Data links for each month.

    For each month, walks the **preorder of elements** from after that month's
    ``<h2>`` up to the next month ``<h2>`` in the requested set, or (for the
    last month) up to the first following ``<h2>`` whose title is *not* in the
    requested set. This includes links inside wrapper ``div``/``section`` blocks
    (February's three list items) while avoiding the previous bug where every
    sibling was scanned for nested month text (nav).

    The DOM structure per month is typically:
    - h2 (month)
    - h3 or p>strong: Data Release, then <ul> of links
    - p>strong: Updated Data, optional paragraphs, then <ul> of links

    For each link, the full ``<li>`` line (not only the anchor) is stored for
    use as the output folder name.
    """
    month_set = {m.strip().lower(): m for m in month_labels}
    payload: Any = page.evaluate(
        """({ monthLabels }) => {
  const wanted = new Set(
    monthLabels.map((m) => (m || "").trim().toLowerCase()).filter(Boolean)
  );

  function textOneLine(el) {
    return (el && el.textContent ? el.textContent : "")
      .replace(/\\s+/g, " ")
      .trim();
  }

  function monthTitleFromH2(h2) {
    return textOneLine(h2);
  }

  function classifyHeadingText(raw) {
    const t = raw.replace(/\\s+/g, " ").trim().toLowerCase();
    if (t === "data release" || t.indexOf("data release") === 0) {
      return "Data Release";
    }
    if (t === "updated data" || t.indexOf("updated data") === 0) {
      return "Updated Data";
    }
    return null;
  }

  function preorderElements(root) {
    const out = [];
    (function w(node) {
      if (!node || node.nodeType !== 1) {
        return;
      }
      out.push(node);
      for (let c = node.firstElementChild; c; c = c.nextElementSibling) {
        w(c);
      }
    })(root);
    return out;
  }

  // Main article body: avoid page chrome / left nav when possible
  const scope =
    document.querySelector(
      "main#content, #content.main, #content, [role=main] main, main, article"
    ) || document.body;

  const h2s = Array.from(scope.querySelectorAll("h2"));
  const monthH2s = h2s.filter((h) => {
    const t = monthTitleFromH2(h);
    return wanted.has(t.toLowerCase());
  });

  // Stable document order
  monthH2s.sort((a, b) => {
    const p = a.compareDocumentPosition(b);
    if (p & Node.DOCUMENT_POSITION_FOLLOWING) {
      return -1;
    }
    if (p & Node.DOCUMENT_POSITION_PRECEDING) {
      return 1;
    }
    return 0;
  });

  const pre = preorderElements(scope);
  const rows = [];

  for (let mi = 0; mi < monthH2s.length; mi++) {
    const h2 = monthH2s[mi];
    const nextInList = monthH2s[mi + 1] || null;
    const a = pre.indexOf(h2);
    if (a < 0) {
      continue;
    }
    let b;
    if (nextInList) {
      b = pre.indexOf(nextInList);
    } else {
      b = pre.length;
      for (let j = a + 1; j < pre.length; j++) {
        const el = pre[j];
        if (el.tagName && el.tagName.toUpperCase() === "H2" && el !== h2) {
          const t = textOneLine(el).toLowerCase();
          if (!wanted.has(t)) {
            b = j;
            break;
          }
        }
      }
    }
    if (b < 0) {
      b = pre.length;
    }
    if (a >= b) {
      continue;
    }

    const monthLabel = monthTitleFromH2(h2);
    let state = null;

    for (let i = a + 1; i < b; i++) {
      const n = pre[i];
      if (!n || !n.tagName) {
        continue;
      }
      const tag = n.tagName.toUpperCase();

      if (/^H[1-6]$/.test(tag)) {
        const cat = classifyHeadingText(textOneLine(n));
        if (cat) {
          state = cat;
        }
        continue;
      }

      if (tag === "P" || tag === "DIV" || tag === "SECTION" || tag === "ARTICLE") {
        if (
          tag === "P" &&
          n.firstElementChild &&
          /^strong|b$/i.test(n.firstElementChild.tagName)
        ) {
          const cat = classifyHeadingText(textOneLine(n.firstElementChild));
          if (cat) {
            state = cat;
            continue;
          }
        }
        const directSB = n.querySelector(":scope > strong, :scope > b");
        if (directSB && (tag === "DIV" || tag === "SECTION" || tag === "ARTICLE")) {
          const cat = classifyHeadingText(textOneLine(directSB));
          if (cat) {
            state = cat;
            continue;
          }
        }
        const ps = n.querySelector(":scope > p > strong, :scope > p > b");
        if (ps) {
          const cat = classifyHeadingText(textOneLine(ps));
          if (cat) {
            state = cat;
            continue;
          }
        }
      }

      if (!state) {
        continue;
      }

      if (tag === "UL" || tag === "OL") {
        const anchors = Array.from(n.querySelectorAll("a[href]"));
        for (const anchor of anchors) {
          const href = (anchor.getAttribute("href") || "").trim();
          if (!href || href === "#" || href.toLowerCase().startsWith("javascript:")) {
            continue;
          }
          const label = textOneLine(anchor) || href;
          const li = anchor.closest("li");
          const listItemText = li
            ? textOneLine(li)
            : (textOneLine(anchor) || href);
          rows.push({
            monthLabel: monthLabel,
            category: state,
            href: href,
            label: label,
            listItemText: listItemText,
          });
        }
      }
    }
  }
  return rows;
}""",
        {"monthLabels": month_labels},
    )

    out: list[ExtractedLink] = []
    if not isinstance(payload, list):
        return out

    seen: set[tuple[str, str, str, str]] = set()
    for row in payload:
        if not isinstance(row, dict):
            continue
        raw_month = str(row.get("monthLabel") or "").strip()
        if not raw_month:
            continue
        canonical = month_set.get(raw_month.lower(), raw_month)
        category = str(row.get("category") or "").strip()
        if category not in ("Data Release", "Updated Data"):
            continue
        href = str(row.get("href") or "").strip()
        if not href:
            continue
        label = str(row.get("label") or "").strip()
        li_text = str(row.get("listItemText") or row.get("label") or "").strip()
        if not li_text:
            li_text = label
        abs_url = urljoin(base_url, href)
        if not _is_nhanes_datapage_href(abs_url):
            continue
        # Some months list different datasets with the same href; distinguish by full <li> text.
        key = (canonical, category, abs_url, _norm_anchor(li_text))
        if key in seen:
            continue
        seen.add(key)
        out.append(
            ExtractedLink(
                month_label=canonical,
                category=category,
                url=abs_url,
                anchor_text=label,
                list_item_text=li_text,
            )
        )

    return out


def _new_context(browser: Browser, *, headless: bool, timeout_ms: int) -> BrowserContext:
    ctx = browser.new_context(
        viewport={"width": 1400, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        timezone_id="America/New_York",
    )
    ctx.set_default_timeout(timeout_ms)
    return ctx


_PDF_MARGINS = {"top": "0.5in", "right": "0.5in", "bottom": "0.5in", "left": "0.5in"}


def _write_page_pdf_to_file(page: Page, pdf_path: Path) -> None:
    page.emulate_media(media="screen")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    page.pdf(
        path=str(pdf_path),
        format="Letter",
        print_background=True,
        margin=_PDF_MARGINS,
    )


def _save_page_pdf(page: Page, out_dir: Path, *, base_url: str) -> Path:
    used: dict[str, int] = {}
    title = page_title_or_h1(page, url=base_url) or "page"
    pdf_name = unique_pdf_basename(title, used=used, folder_path=out_dir)
    pdf_path = out_dir / pdf_name
    _write_page_pdf_to_file(page, pdf_path)
    return pdf_path


def _is_bad_social_or_share_url(url: str) -> bool:
    u = (url or "").lower()
    for bad in (
        "facebook.com",
        "twitter.com",
        "linkedin.com/sharing",
        "linkedin.com/share",
        "addthis.com",
        "pinterest",
        "tools.cdc.gov/medialibrary",
    ):
        if bad in u:
            return True
    return False


def _url_equal_skipping_fragment(a: str, b: str) -> bool:
    pa, pb = urlparse(a), urlparse(b)
    if (pa.netloc, pa.path) != (pb.netloc, pb.path):
        return False
    return parse_qs(pa.query) == parse_qs(pb.query)


def _path_is_variable_list(url: str) -> bool:
    return "variablelist.aspx" in (url or "").lower()


def _path_is_lab_methods(url: str) -> bool:
    p = (url or "").lower()
    return "labmethods.aspx" in p or "/labmethods" in p


def _path_is_exam_manuals(url: str) -> bool:
    p = (url or "").lower()
    return "manuals.aspx" in p and "continuousnhanes" in p


def _extract_data_page_nav_list(page: Page) -> list[dict[str, str]]:
    """Return ``[{text, href}, ...]`` for the bullet list that includes Variable List."""
    raw: Any = page.evaluate(
        """() => {
  const a0 = document.querySelector(
    'main a[href*="variablelist.aspx"], #content a[href*="variablelist.aspx"]'
  );
  if (!a0) {
    return [];
  }
  const ul = a0.closest("ul");
  if (!ul) {
    return [];
  }
  const out = [];
  for (const a of ul.querySelectorAll("a[href]")) {
    const href = (a.getAttribute("href") || "").trim();
    if (!href || href === "#" || href.toLowerCase().startsWith("javascript:")) {
      continue;
    }
    const t = (a.textContent || "").replace(/\\s+/g, " ").trim();
    out.push({ text: t || href, href: href });
  }
  return out;
}"""
    )
    if not isinstance(raw, list):
        return []
    return [r for r in raw if isinstance(r, dict) and r.get("href")]


def _click_print_link_then_write_pdf(page: Page, pdf_path: Path) -> None:
    """Click the in-page ``#print`` control, then write a print-style PDF (do not reset to screen first)."""
    try:
        loc = page.locator('main a[href="#print"], #content a[href="#print"]')
        if not loc.count():
            loc = page.locator('a[href="#print"]')
        if loc.count():
            for i in range(min(loc.count(), 5)):
                el = loc.nth(i)
                if el.is_visible():
                    el.click()
                    break
        page.wait_for_timeout(1500)
    except Exception:
        pass
    page.emulate_media(media="print")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    page.pdf(
        path=str(pdf_path),
        format="Letter",
        print_background=True,
        margin=_PDF_MARGINS,
    )


def _extract_documentation_table_pdf_hrefs(page: Page) -> list[tuple[str, str]]:
    """
    (row_label, pdf_href) from tables with a Document / Documentation column. ``href`` is as in DOM.
    """
    raw: Any = page.evaluate(
        r"""() => {
  const t = (s) => (s || "").replace(/\s+/g, " ").trim();
  const out = [];
  const isPdf = (h) => {
    const x = (h || "").split("?")[0].toLowerCase();
    return x.endsWith(".pdf");
  };
  for (const tb of document.querySelectorAll("table")) {
    const tr0 = tb.querySelector("tr");
    if (!tr0) {
      continue;
    }
    const headerCells = Array.from(tr0.querySelectorAll("th, td"));
    const docIdx = headerCells.findIndex((c) => {
      const x = t(c.textContent);
      if (!x) {
        return false;
      }
      const xl = x.toLowerCase();
      if (xl === "documentation" || xl === "document") {
        return true;
      }
      return false;
    });
    if (docIdx < 0) {
      continue;
    }
    for (const tr of Array.from(tb.querySelectorAll("tr")).slice(1)) {
      const cells = Array.from(tr.querySelectorAll("th, td"));
      if (cells.length === 0) {
        continue;
      }
      const nameCell = cells[0];
      const rowName = t(nameCell ? nameCell.textContent : "");
      const docCell = cells[docIdx];
      if (!docCell) {
        continue;
      }
      for (const a of docCell.querySelectorAll("a[href]")) {
        const h = (a.getAttribute("href") || "").trim();
        if (h && isPdf(h)) {
          out.push([rowName, h]);
        }
      }
    }
  }
  return out;
}"""
    )
    if not isinstance(raw, list):
        return []
    out: list[tuple[str, str]] = []
    for row in raw:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            continue
        rn, h = str(row[0]), str(row[1])
        if h:
            out.append((rn, h))
    return out


def _stream_download(
    target_url: str, dest: Path, page: Page, *, timeout_s: int = 300
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    out_candidates: list[str] = [str(dest)]
    if os.name == "nt":
        try:
            ex = "\\\\?\\" + str(dest.resolve())
        except OSError:
            ex = None
        if ex and ex not in out_candidates and not str(dest).startswith("\\\\?\\"):
            out_candidates.insert(0, ex)

    def _requests_stream_to(path: str) -> None:
        with requests.get(
            target_url,
            stream=True,
            timeout=timeout_s,
            headers={"User-Agent": ua},
        ) as r:
            r.raise_for_status()
            with open(path, "wb") as f:  # noqa: SIM115
                for chunk in r.iter_content(65536):
                    if chunk:
                        f.write(chunk)

    last: Exception | None = None
    for path in out_candidates:
        try:
            _requests_stream_to(path)
            return
        except (OSError, FileNotFoundError) as e:
            last = e
            continue
    if last is not None:
        Logger.debug("requests stream to disk failed, trying context.request: %s", last)
    r2 = page.context.request.get(target_url, timeout=timeout_s * 1000)
    if not r2.ok:
        raise RuntimeError(f"Download failed {r2.status}: {target_url}")
    data = r2.body()
    for path in out_candidates:
        try:
            with open(path, "wb") as f:  # noqa: SIM115
                f.write(data)
            return
        except OSError as e2:
            last = e2
    raise OSError(f"Could not write download to {dest}") from last


def _unique_pdf_path_in_dir(
    link_dir: Path,
    base_stem: str,
    used: dict[str, int],
    *,
    max_stem: int = _STEM_MAX_RELATED_PDF,
) -> Path:
    """Return a path ``link_dir / name.pdf`` that does not exist on disk."""
    safe = _shorten_filename_stem((base_stem or "").strip(), max_stem)
    safe = sanitize_filename(safe, max_length=max_stem + 8)
    if not safe:
        safe = "page"
    key = safe.lower()
    n = used.get(key, 0)
    while True:
        name = f"{safe}.pdf" if n == 0 else f"{safe}_{n}.pdf"
        n += 1
        path = link_dir / name
        if path.exists():
            continue
        used[key] = n
        return path


def _local_filename_for_download_url(abs_url: str) -> str:
    """Derive a safe on-disk name from a download URL (path last segment)."""
    path = (urlparse(abs_url).path or "").rstrip("/")
    base = path.rsplit("/", 1)[-1] if path else "download"
    if not base or base in (".", ".."):
        base = "download"
    return sanitize_filename(base, max_length=150) or "download"


def _extract_data_file_table_rows(page: Page) -> list[dict[str, str]]:
    """Parse the Data / Doc / file table on a Search DataPage. Expects the page to be open."""
    raw: Any = page.evaluate(
        r"""() => {
  const t = (s) => (s || "").replace(/\s+/g, " ").trim();
  const out = [];
  for (const tb of document.querySelectorAll("table")) {
    const tr0 = tb.querySelector("tr");
    if (!tr0) {
      continue;
    }
    const headers = Array.from(tr0.querySelectorAll("th, td")).map((c) => t(c.textContent));
    const iName = headers.findIndex((h) => /data file name/i.test(h));
    if (iName < 0) {
      continue;
    }
    const iDoc = headers.findIndex((h) => h.trim().toLowerCase() === "doc file");
    const iData = headers.findIndex((h) => h.trim().toLowerCase() === "data file");
    const iDate = headers.findIndex((h) => /date published/i.test(h));
    if (iDoc < 0 || iData < 0) {
      continue;
    }
    const rowEls = tb.querySelector("tbody")
      ? Array.from(tb.querySelectorAll("tbody tr"))
      : Array.from(tb.querySelectorAll("tr")).filter((r) => r !== tr0);
    for (const tr of rowEls) {
      if (tr === tr0) {
        continue;
      }
      const cells = tr.querySelectorAll("td, th");
      if (cells.length < Math.max(iName, iDoc, iData) + 1) {
        continue;
      }
      const g = (i) => (cells[i] ? cells[i] : null);
      const name = t(g(iName) ? g(iName).textContent : "");
      if (!name || /^data file name$/i.test(name)) {
        continue;
      }
      const aDoc = g(iDoc) ? g(iDoc).querySelector("a[href]") : null;
      const aData = g(iData) ? g(iData).querySelector("a[href]") : null;
      const hrefDoc = aDoc ? (aDoc.getAttribute("href") || "").trim() : "";
      const hrefData = aData ? (aData.getAttribute("href") || "").trim() : "";
      const datePub = iDate >= 0 && g(iDate) ? t(g(iDate).textContent) : "";
      if (!hrefDoc && !hrefData) {
        continue;
      }
      out.push({
        dataFileName: name,
        docHref: hrefDoc,
        dataHref: hrefData,
        datePublished: datePub,
      });
    }
  }
  return out;
}"""
    )
    if not isinstance(raw, list):
        return []
    out2: list[dict[str, str]] = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        out2.append(
            {
                "dataFileName": str(r.get("dataFileName") or "").strip(),
                "docHref": str(r.get("docHref") or "").strip(),
                "dataHref": str(r.get("dataHref") or "").strip(),
                "datePublished": str(r.get("datePublished") or "").strip(),
            }
        )
    return out2


def _process_data_file_table_row_downloads(
    page: Page,
    link_dir: Path,
    data_page_url: str,
    *,
    max_data_file_rows: int,
) -> int:
    """
    For each table row (Data File Name, Doc File, Data File, Date Published),
    create a subfolder under ``link_dir`` and download the doc and data links.
    The Data page must already be loaded in ``page``.
    Returns the number of row folders that received at least one file.
    """
    rows = _extract_data_file_table_rows(page)
    if not rows:
        Logger.info("  (no Data File Name / Doc / Data table; skipping data-file downloads)")
        return 0
    nlim = int(max_data_file_rows)
    if nlim > 0 and len(rows) > nlim:
        Logger.info("  limiting data-file table to %d of %d rows", nlim, len(rows))
        rows = rows[:nlim]
    used_sub: dict[str, int] = {}
    done_row: set[str] = set()
    n_folders_with_file = 0
    for row in rows:
        name = (row.get("dataFileName") or "").strip()
        d_doc = (row.get("docHref") or "").strip()
        d_data = (row.get("dataHref") or "").strip()
        if not name:
            continue
        if not d_doc and not d_data:
            continue
        dedup = f"{_norm_anchor(name)}|{d_doc}|{d_data}"
        if dedup in done_row:
            continue
        done_row.add(dedup)
        sub = link_dir / _unique_sanitized_dirname(
            name, used_sub, link_dir, max_len=_STEM_MAX_DATA_FILE_SUBFOLDER
        )
        _ensure_dir(sub)
        n_here = 0
        for label, rel in (("doc", d_doc), ("data", d_data)):
            if not rel:
                continue
            u = urljoin(data_page_url, rel)
            dest = sub / _local_filename_for_download_url(u)
            try:
                if dest.exists():
                    try:
                        if dest.stat().st_size > 0:
                            n_here += 1
                            Logger.info(
                                "  data table [%s] %s (skip, exists): %s",
                                label,
                                name[:50],
                                dest.name,
                            )
                            continue
                    except OSError:
                        pass
                _stream_download(u, dest, page)
                n_here += 1
                Logger.info("  data table [%s] %s -> %s", label, name[:50], dest.name)
            except Exception:  # noqa: BLE001
                Logger.exception("  data table download failed: %s -> %s", name[:50], u)
        if n_here > 0:
            n_folders_with_file += 1
    Logger.info("  data-file table: %d row folder(s) with downloads", n_folders_with_file)
    return n_folders_with_file


def _process_data_page_related_links(
    page: Page,
    link_dir: Path,
    data_page_url: str,
    *,
    max_documentation_pdfs: int,
) -> None:
    """
    On the NHANES Search Data page, follow the in-content bullet list (the one
    with Variable List) and record PDFs / downloaded docs under ``link_dir``.
    """
    nav = _extract_data_page_nav_list(page)
    if not nav:
        Logger.info("  (no in-page data nav list found; skipping related links)")
        return

    used_flat_pdf: dict[str, int] = {}
    used_subdir: dict[str, int] = {}
    done_keys: set[str] = set()
    for item in nav:
        text = str(item.get("text") or "").strip()
        href = str(item.get("href") or "").strip()
        if not text or not href:
            continue
        abs_u = urljoin(data_page_url, href)
        if _is_bad_social_or_share_url(abs_u):
            continue
        if _url_equal_skipping_fragment(abs_u, data_page_url):
            continue
        dkey = f"{_norm_anchor(text)}|{abs_u}"
        if dkey in done_keys:
            continue
        done_keys.add(dkey)

        Logger.info("  + related: %s -> %s", text[:90], abs_u)
        t0 = time.time()
        try:
            page.goto(abs_u, wait_until="domcontentloaded")
            page.wait_for_timeout(1000)
        except Exception:
            Logger.exception("  failed to open related URL %s", abs_u)
            continue

        if _path_is_variable_list(abs_u):
            out_pdf = _unique_pdf_path_in_dir(
                link_dir, text, used_flat_pdf, max_stem=_STEM_MAX_RELATED_PDF
            )
            try:
                _click_print_link_then_write_pdf(page, out_pdf)
            except Exception:
                Logger.warning("  print-link PDF failed, falling back to screen PDF: %s", out_pdf.name)
                _write_page_pdf_to_file(page, out_pdf)
            Logger.info("  saved %s (%.1fs)", out_pdf, time.time() - t0)
            continue

        if _path_is_lab_methods(abs_u) or _path_is_exam_manuals(abs_u):
            sub = link_dir / _unique_sanitized_dirname(
                text, used_subdir, link_dir, max_len=_STEM_MAX_METHODS_SUBFOLDER
            )
            _ensure_dir(sub)
            idx_pdf = sub / "index.pdf"
            n_doc_this = 0
            try:
                _write_page_pdf_to_file(page, idx_pdf)
            except Exception:
                Logger.exception("  page PDF for %s", abs_u)
            doc_dir = sub / "Documentation"
            _ensure_dir(doc_dir)
            rows = _extract_documentation_table_pdf_hrefs(page)
            used_pdf: dict[str, int] = {}
            for row_name, p_href in rows:
                if max_documentation_pdfs > 0 and n_doc_this >= max_documentation_pdfs:
                    Logger.info(
                        "  reached --max-documentation-pdfs (%d) for this page; stopping",
                        max_documentation_pdfs,
                    )
                    break
                target = urljoin(abs_u, p_href)
                base_name = (row_name or Path(p_href).stem or "doc").strip()
                if not base_name or base_name == "…":
                    base_name = Path(urlparse(target).path).stem or "doc"
                out_f = _unique_pdf_path_in_dir(
                    doc_dir, base_name, used_pdf, max_stem=_STEM_MAX_DOC_PDF
                )
                try:
                    _stream_download(target, out_f, page)
                    n_doc_this += 1
                except Exception:
                    Logger.exception("  download %s", target)
            Logger.info("  methods/manuals: %s (%.1fs, %d doc PDFs saved)", sub.name, time.time() - t0, n_doc_this)
            continue

        out_pdf = _unique_pdf_path_in_dir(
            link_dir, text, used_flat_pdf, max_stem=_STEM_MAX_RELATED_PDF
        )
        try:
            _write_page_pdf_to_file(page, out_pdf)
        except Exception:
            Logger.exception("  PDF for %s", abs_u)
        else:
            Logger.info("  saved %s (%.1fs)", out_pdf, time.time() - t0)


def _iter_unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        k = (x or "").strip()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect CDC NHANES Latest page PDFs (sidebar months).")
    parser.add_argument("--home-url", default=DEFAULT_HOME_URL, help="CDC NHANES Latest Data Releases URL.")
    parser.add_argument(
        "--dest",
        default=r"C:\Documents\DataRescue\CDCData\DRP000001",
        help="Destination folder (DRP000001).",
    )
    parser.add_argument(
        "--months",
        nargs="*",
        default=DEFAULT_MONTHS,
        help="Month labels to scrape (default: March/February/January 2026).",
    )
    parser.add_argument("--headless", action="store_true", help="Run Playwright headless.")
    parser.add_argument("--timeout-ms", type=int, default=60_000, help="Playwright default timeout (ms).")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max list items per month **and** category (Data Release / Updated Data); 0 = no limit.",
    )
    parser.add_argument(
        "--no-related",
        action="store_true",
        help="Do not follow the Data page bullet list (Variable List, methods, etc.).",
    )
    parser.add_argument(
        "--max-documentation-pdfs",
        type=int,
        default=0,
        help="Max documentation PDFs to download per Lab Methods / Exam Manuals page (0 = no limit).",
    )
    parser.add_argument(
        "--no-data-file-table",
        action="store_true",
        help="Do not download Doc File / Data File rows from the main Data page table.",
    )
    parser.add_argument(
        "--max-data-file-rows",
        type=int,
        default=0,
        help="Max rows to process from the Data File Name table per Data page (0 = all rows).",
    )
    args = parser.parse_args(argv)

    Logger.initialize(log_level="INFO")

    dest_root = Path(args.dest)
    _ensure_dir(dest_root)
    months = _iter_unique(args.months)
    if not months:
        Logger.error("No months requested.")
        return 2

    Logger.info("Home: %s", args.home_url)
    Logger.info("Dest: %s", str(dest_root))
    Logger.info("Months: %s", ", ".join(months))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=bool(args.headless))
        context = _new_context(browser, headless=bool(args.headless), timeout_ms=int(args.timeout_ms))
        page = context.new_page()

        Logger.info("Loading home page")
        page.goto(args.home_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)

        extracted = _extract_main_column_links(page, base_url=args.home_url, month_labels=months)
        if not extracted:
            Logger.error("No links found for requested months (Data Release / Updated Data).")
            Logger.error("Tip: try running with --headless=false and inspect the page structure.")
            return 3

        by_month_cat: dict[tuple[str, str], list[ExtractedLink]] = {}
        for e in extracted:
            by_month_cat.setdefault((e.month_label, e.category), []).append(e)

        for m in months:
            n_dr = len(by_month_cat.get((m, "Data Release"), []))
            n_ud = len(by_month_cat.get((m, "Updated Data"), []))
            Logger.info("%s: Data Release %d, Updated Data %d", m, n_dr, n_ud)

        for month_label in months:
            month_dir = dest_root / _month_dir_name(month_label)
            for category in ("Data Release", "Updated Data"):
                links = by_month_cat.get((month_label, category), [])
                if not links:
                    continue
                if int(args.limit) > 0:
                    links = links[: int(args.limit)]

                cat_dir = month_dir / _category_dir_name(category)
                _ensure_dir(cat_dir)
                used_dirs: dict[str, int] = {}

                for idx, link in enumerate(links, start=1):
                    Logger.info(
                        "[%s / %s %d/%d] %s",
                        month_label,
                        category,
                        idx,
                        len(links),
                        link.url,
                    )
                    t0 = time.time()
                    try:
                        page.goto(link.url, wait_until="domcontentloaded")
                        page.wait_for_timeout(1000)
                        folder = _unique_sanitized_dirname(
                            link.list_item_text, used_dirs, cat_dir, max_len=_STEM_MAX_LIST_FOLDER
                        )
                        link_dir = cat_dir / folder
                        _ensure_dir(link_dir)

                        pdf_path = _save_page_pdf(page, link_dir, base_url=link.url)
                        Logger.info("  data page PDF: %s", pdf_path.name)

                        meta: dict[str, Any] = {
                            "month": month_label,
                            "category": category,
                            "anchor_text": link.anchor_text,
                            "list_item_text": link.list_item_text,
                            "folder_from_list_item": folder,
                            "url": link.url,
                            "saved_pdf": str(pdf_path),
                            "saved_at_unix": time.time(),
                            "page_title": page.title(),
                        }
                        if not args.no_data_file_table:
                            n_df = _process_data_file_table_row_downloads(
                                page,
                                link_dir,
                                link.url,
                                max_data_file_rows=int(args.max_data_file_rows),
                            )
                            meta["data_file_table_row_folders"] = n_df
                        else:
                            meta["data_file_table_skipped"] = True
                        if not args.no_related:
                            _process_data_page_related_links(
                                page,
                                link_dir,
                                link.url,
                                max_documentation_pdfs=int(args.max_documentation_pdfs),
                            )
                        else:
                            meta["related_links_skipped"] = True
                        (link_dir / "source.json").write_text(
                            json.dumps(meta, indent=2, default=str), encoding="utf-8"
                        )
                        Logger.info("Finished %s (%.1fs)", folder, time.time() - t0)
                    except Exception:
                        Logger.exception("Failed on %s", link.url)
                        continue

        context.close()
        browser.close()

    Logger.info("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

