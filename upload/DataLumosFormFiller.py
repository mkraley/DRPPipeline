"""
DataLumos form field population.

Handles filling all form fields on the DataLumos project page
including text inputs, WYSIWYG editors, dropdowns, and autocomplete fields.
"""

import re
from typing import List, Optional, TYPE_CHECKING

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from utils.Logger import Logger

if TYPE_CHECKING:
    from upload.UploadIssueReporter import UploadIssueReporter

DATALUMOS_TITLE_MAX_LENGTH = 250


def truncate_title_for_datalumos(title: str, max_len: int = DATALUMOS_TITLE_MAX_LENGTH) -> str:
    """
    Truncate a project title to DataLumos's length limit without breaking mid-word when possible.

    Normalizes whitespace, then if still over ``max_len`` cuts at the last space in the
    allowed span (when that keeps most of the title). Otherwise hard-truncates.
    Appends an ellipsis when text was removed.
    """
    normalized = " ".join(title.split())
    if len(normalized) <= max_len:
        return normalized

    suffix = "…"
    if max_len <= len(suffix):
        return normalized[:max_len]

    cut_at = max_len - len(suffix)
    candidate = normalized[:cut_at]
    last_space = candidate.rfind(" ")
    min_word_break = int(cut_at * 0.6)
    if last_space >= min_word_break:
        candidate = candidate[:last_space]

    return candidate.rstrip(" ,;:-") + suffix


def _is_empty(value: Optional[str]) -> bool:
    """Return True if value is None, empty, or whitespace-only."""
    return not value or value.strip() == ""


def _debug_form_field(name: str, value: Optional[str] = None, *, n_chars: Optional[int] = None) -> None:
    """Log a single form field at DEBUG as it is filled (value may be long HTML)."""
    if n_chars is not None:
        Logger.debug(f"Upload form field {name}: {n_chars} character(s)")
        return
    if value is None:
        Logger.debug(f"Upload form field {name}: (none)")
        return
    preview = value.replace("\n", " ").strip()
    if len(preview) > 140:
        preview = preview[:140] + "…"
    Logger.debug(f"Upload form field {name}: {preview!r}")


class DataLumosFormFiller:
    """
    Fills form fields on the DataLumos project page.
    
    Handles different input types:
    - Text inputs
    - WYSIWYG editors (iframe-based)
    - Dropdown selections
    - Autocomplete/tag inputs (select2)
    """
    
    def __init__(
        self,
        page: Page,
        timeout: int = 2000,
        reporter: Optional["UploadIssueReporter"] = None,
    ) -> None:
        """
        Initialize the form filler.
        
        Args:
            page: Playwright Page object
            timeout: Default timeout in milliseconds
            reporter: When set, warnings are persisted to the project record
        """
        self._page = page
        self._timeout = timeout
        self._reporter = reporter

    def _warn(self, msg: str) -> None:
        if self._reporter is not None:
            self._reporter.warn(msg)
        else:
            Logger.warning(msg)
    
    def wait_for_obscuring_elements(self) -> None:
        """
        Wait for any loading overlays or busy indicators to disappear.
        
        Looks for elements with id="busy" and waits for them to become hidden.
        """
        busy_locator = self._page.locator("#busy")
        try:
            if busy_locator.count() > 0:
                busy_locator.first.wait_for(state="hidden", timeout=360000)  # 6 min
                self._page.wait_for_timeout(500)
        except PlaywrightTimeoutError:
            self._warn("Timeout waiting for busy overlay to disappear")
    
    def expand_all_sections(self) -> None:
        """
        Expand all collapsible sections on the form.

        Clicks "Collapse All" then "Expand All" to ensure all sections are visible.
        Non-fatal if the toggle is missing (DataLumos UI changes).
        """
        try:
            collapse_btn = self._page.locator("#expand-init > span:nth-child(2)")
            self.wait_for_obscuring_elements()
            collapse_btn.click(timeout=5000)
            self._page.wait_for_timeout(2000)

            expand_btn = self._page.locator("#expand-init > span:nth-child(2)")
            self.wait_for_obscuring_elements()
            expand_btn.click(timeout=5000)
            self._page.wait_for_timeout(2000)
        except PlaywrightTimeoutError:
            self._warn("expand_all_sections: #expand-init not found, skipping")
    
    def fill_title(self, title: str) -> None:
        """
        Fill the project title field and create the project.
        
        Args:
            title: Project title text
        """
        truncated = truncate_title_for_datalumos(title)
        if len(truncated) < len(" ".join(title.split())):
            self._warn(
                f"Title truncated from {len(' '.join(title.split()))} to "
                f"{len(truncated)} characters for DataLumos limit"
            )
        _debug_form_field("title", truncated)
        title_input = self._page.locator("#title")
        title_input.fill(truncated)

        save_apply_btn = self._page.get_by_role(
            "button", name=re.compile(r"Save\s*&\s*Apply", re.I)
        )
        self.wait_for_obscuring_elements()
        save_apply_btn.click()

        continue_btn = self._page.get_by_role("button", name="Continue To Project Workspace")
        self.wait_for_obscuring_elements()
        continue_btn.click()
        
        self.wait_for_obscuring_elements()
        self._page.wait_for_timeout(1000)
    
    def fill_agency(self, agencies: List[str]) -> None:
        """
        Fill the government agency field(s).
        
        Adds agency and office as separate values. Each non-empty value
        opens the add-value modal, selects Organization/Agency tab,
        fills orgName, and saves.
        
        Args:
            agencies: List of agency/office names to add (e.g. [agency, office])
        """
        add_value_selector = (
            "#groupAttr0 > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > "
            "a:nth-child(3) > span:nth-child(3)"
        )
        
        for value in agencies:
            if _is_empty(value):
                continue
            
            value = value.strip()
            if value == 'CDC':
                value = 'United States Department of Health and Human Services. Centers for Disease Control and Prevention'
            _debug_form_field("agency_or_office", value)
            add_btn = self._page.locator(add_value_selector)
            self.wait_for_obscuring_elements()
            add_btn.click()
            
            # Element: <a href="#org" role="tab">Organization/Agency</a> - use href (role="tab" not "link")
            agency_tab = self._page.locator('a[href="#org"]')
            self.wait_for_obscuring_elements()
            agency_tab.click()
            
            org_field = self._page.locator("#orgName")
            org_field.fill(value)
            self._page.wait_for_timeout(500)
            
            self._dismiss_autocomplete_dropdown()
            
            self.wait_for_obscuring_elements()
            submit_btn = self._page.locator(".save-org")
            submit_btn.click()
    
    def _dismiss_autocomplete_dropdown(self) -> None:
        """Dismiss any open autocomplete dropdown."""
        try:
            label = self._page.locator("label[for='orgName']")
            if label.is_visible(timeout=1000):
                label.click()
        except PlaywrightTimeoutError:
            try:
                label = self._page.locator(
                    "xpath=//label[contains(text(), 'Organization') or contains(text(), 'Agency')]"
                )
                if label.first.is_visible(timeout=1000):
                    label.first.click()
            except PlaywrightTimeoutError:
                try:
                    header = self._page.locator(".modal-header, .modal-title").first
                    if header.is_visible(timeout=1000):
                        header.click()
                except PlaywrightTimeoutError:
                    self._page.keyboard.press("Escape")
        
        self._page.wait_for_timeout(300)
    
    def fill_summary(self, summary: str) -> None:
        """Fill the summary/description field (WYSIWYG). Preserves HTML markup."""
        if _is_empty(summary):
            return
        _debug_form_field("summary (dcterms_description)", n_chars=len(summary))
        self._fill_wysiwyg(
            "#edit-dcterms_description_0",
            summary,
            "#groupAttr0 iframe.wysihtml5-sandbox",
            ".glyphicon-ok",
        )
    
    def fill_original_url(self, url: str) -> None:
        """Fill the original distribution URL field."""
        if _is_empty(url):
            return
        _debug_form_field("original_distribution_url (imeta_sourceURL)", url)
        self._fill_editable_inline(
            "#edit-imeta_sourceURL_0 > span:nth-child(1) > span:nth-child(2)",
            url,
        )
    
    def fill_keywords(self, keywords: List[str]) -> None:
        """
        Fill the subject terms/keywords field.
        
        Uses select2 autocomplete - types each keyword and selects
        the matching suggestion.
        """
        for keyword in keywords:
            keyword = keyword.strip(" '")
            if len(keyword) <= 2:
                continue
            
            try:
                self.wait_for_obscuring_elements()
                _debug_form_field("keyword (subject term)", keyword)
                search_field = self._page.locator(".select2-search__field")
                search_field.click()
                search_field.fill(keyword)
                self.wait_for_obscuring_elements()
                
                option = self._page.locator(
                    f"xpath=//li[contains(@class, 'select2-results__option') and text()='{keyword}']"
                )
                self.wait_for_obscuring_elements()
                option.click()
            except PlaywrightTimeoutError as e:
                self._warn(f"Could not add keyword '{keyword}': {e}")
    
    def _geographic_coverage_block(self):
        """Geographic coverage field container: label span, up two parent levels."""
        label = self._page.locator("span").filter(
            has_text=re.compile(r"Geographic coverage", re.I)
        ).first
        label.wait_for(state="visible", timeout=50000)
        return label.locator("xpath=./parent::*/parent::*")

    def _click_geographic_add_value(self) -> None:
        self.wait_for_obscuring_elements()
        block = self._geographic_coverage_block()
        block.scroll_into_view_if_needed()
        add_btn = block.get_by_title(re.compile(r"^add value$", re.I))
        add_btn.wait_for(state="visible", timeout=50000)
        add_btn.click()

    def _add_geographic_term(self, term: str) -> None:
        """Add one ICPSR geographic term via add-value, then modal or inline input."""
        self._click_geographic_add_value()

        geo_field = self._page.locator("#geoName")
        if geo_field.count() > 0:
            geo_field.first.wait_for(state="visible", timeout=50000)
            geo_field.first.fill(term)
            self._page.wait_for_timeout(500)
            save = self._page.locator(".save-geo")
            save.first.wait_for(state="visible", timeout=50000)
            save.first.click()
            self.wait_for_obscuring_elements()
            return

        url_input = self._page.locator(".editable-input > input:nth-child(1)").first
        url_input.wait_for(state="visible", timeout=50000)
        self.wait_for_obscuring_elements()
        url_input.fill(term)
        url_input.press("Enter")
        self.wait_for_obscuring_elements()

    def fill_geographic_coverage(self, coverage: str) -> None:
        """
        Fill the geographic coverage field with one or more ICPSR thesaurus terms.

        ``coverage`` is semicolon-delimited. Each term uses the section's
        ``add value`` link (title="add value") beside the Geographic coverage label.
        """
        from utils.IcpsrGeographicNormalizer import parse_geographic_coverage_field

        terms = parse_geographic_coverage_field(coverage)
        if not terms:
            return

        for term in terms:
            _debug_form_field("geographic_coverage (dcterms_location)", term)
            try:
                self._add_geographic_term(term)
            except PlaywrightTimeoutError as exc:
                self._warn(f"Could not add geographic term '{term}': {exc}")
    
    def fill_time_period(self, start: Optional[str], end: Optional[str]) -> None:
        """Fill the time period fields."""
        if _is_empty(start) and _is_empty(end):
            return

        _debug_form_field("time_period", f"start={start!r} end={end!r}")

        add_btn = self._page.locator(
            "#groupAttr1 > div:nth-child(1) > div:nth-child(3) > div:nth-child(1) > "
            "a:nth-child(3) > span:nth-child(3)"
        )
        add_btn.wait_for(state="visible", timeout=50000)
        self.wait_for_obscuring_elements()
        add_btn.click()
        
        start_input = self._page.locator("#startDate")
        start_input.wait_for(state="visible", timeout=50000)
        self.wait_for_obscuring_elements()
        start_input.fill(start or "")
        
        end_input = self._page.locator("#endDate")
        end_input.wait_for(state="visible", timeout=50000)
        self.wait_for_obscuring_elements()
        end_input.fill(end or "")
        
        save_btn = self._page.locator(".save-dates")
        save_btn.wait_for(state="visible", timeout=50000)
        self.wait_for_obscuring_elements()
        save_btn.click()
        self.wait_for_obscuring_elements()

        # The time period modal (React-managed) intercepts pointer events on subsequent
        # fields if it stays open. Press Escape to dismiss it, then wait for the fade-out
        # animation to complete before returning.
        self._page.keyboard.press("Escape")
        try:
            self._page.locator(".modal.fade.in").wait_for(state="hidden", timeout=10000)
        except PlaywrightTimeoutError:
            self._warn("Time period modal still visible after Escape; continuing anyway")
            self._page.wait_for_timeout(1000)

    def fill_data_types(self, data_type: str) -> None:
        """
        Fill the data types field by selecting one or more checklist options.

        ``data_type`` may be a single label or several labels separated by semicolons.
        After clicking edit, an editable-checklist appears with label+span options.
        Clicks each label (not span) scoped to the checklist, then saves once.
        """
        if _is_empty(data_type):
            return

        data_types = [part.strip() for part in re.split(r"\s*;\s*", data_type) if part.strip()]
        if not data_types:
            return

        _debug_form_field("data_types (kindOfData)", "; ".join(data_types))

        edit_btn = self._page.locator("#disco_kindOfData_0 > span:nth-child(2)")
        self.wait_for_obscuring_elements()
        edit_btn.click()
        self.wait_for_obscuring_elements()

        for label in data_types:
            # Double-quote wrapper handles apostrophes; escape any internal double quotes
            safe = label.replace('"', '\\"')
            datatype_label = self._page.locator(
                f'.editable-checklist label:has(span:has-text("{safe}"))'
            )
            datatype_label.click()

        save_btn = self._page.locator(".editable-submit")
        save_btn.click()
    
    def fill_collection_notes(self, notes: str, download_date: Optional[str] = None) -> None:
        """Fill the collection notes field, optionally appending download date."""
        download_part = f"(Downloaded {download_date})" if download_date else ""
        text = (notes or "").strip()
        if text and download_part:
            combined = f"{text} {download_part}"
        elif download_part:
            combined = download_part
        else:
            return

        _debug_form_field("collection_notes (imeta_collectionNotes)", n_chars=len(combined))

        self._fill_wysiwyg(
            "#edit-imeta_collectionNotes_0",
            combined,
            "#groupAttr1 iframe.wysihtml5-sandbox",
            ".editable-submit",
        )
    
    def _fill_editable_inline(
        self,
        edit_selector: str,
        value: str,
        *,
        fallback_selectors: List[str] | None = None,
    ) -> None:
        """
        Fill an inline-editable field (click edit, type in input, submit).

        Args:
            edit_selector: Selector for the edit button
            value: Value to fill
            fallback_selectors: Additional edit-button selectors to try
        """
        edit_btn = None
        for sel in [edit_selector, *(fallback_selectors or [])]:
            candidate = self._page.locator(sel).first
            try:
                candidate.wait_for(state="visible", timeout=5000)
                edit_btn = candidate
                break
            except PlaywrightTimeoutError:
                continue
        if edit_btn is None:
            raise PlaywrightTimeoutError(f"Edit control not found: {edit_selector}")

        self.wait_for_obscuring_elements()
        edit_btn.click()

        url_input = self._page.locator(".editable-input > input:nth-child(1)").first
        url_input.wait_for(state="visible", timeout=50000)
        self.wait_for_obscuring_elements()
        url_input.fill(value)
        url_input.press("Enter")
    
    def _fill_wysiwyg(
        self, edit_selector: str, text: str, frame_selector: str, save_selector: str
    ) -> None:
        """
        Fill a WYSIWYG editor field (iframe-based).

        Sets the iframe body's innerHTML so HTML markup (paragraphs, links,
        bold, etc.) is rendered as rich text rather than literal tags.

        Args:
            edit_selector: Selector for the edit button
            text: HTML or plain text to set in the editor body
            frame_selector: Selector for the editor iframe
            save_selector: Selector for the save button
        """
        edit_btn = self._page.locator(edit_selector)
        self.wait_for_obscuring_elements()
        edit_btn.click()

        frame = self._page.frame_locator(frame_selector)
        body = frame.locator("body")
        body.click()
        self._page.wait_for_timeout(300)

        body.evaluate(
            """(el, html) => {
                el.innerHTML = html;
                el.dispatchEvent(new Event('input', { bubbles: true }));
            }""",
            text,
        )
        self._page.wait_for_timeout(300)
        
        self.wait_for_obscuring_elements()
        save_btn = self._page.locator(save_selector).first
        self.wait_for_obscuring_elements()
        save_btn.click()
