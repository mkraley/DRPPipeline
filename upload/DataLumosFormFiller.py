"""
DataLumos form field population.

Handles filling all form fields on the DataLumos project page
including text inputs, WYSIWYG editors, dropdowns, and autocomplete fields.
"""

from typing import List, Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from utils.Logger import Logger


class DataLumosFormFiller:
    """
    Fills form fields on the DataLumos project page.
    
    Handles different input types:
    - Text inputs
    - WYSIWYG editors (iframe-based)
    - Dropdown selections
    - Autocomplete/tag inputs (select2)
    """
    
    def __init__(self, page: Page, timeout: int = 30000) -> None:
        """
        Initialize the form filler.
        
        Args:
            page: Playwright Page object
            timeout: Default timeout in milliseconds
        """
        self._page = page
        self._timeout = timeout
    
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
            Logger.warning("Timeout waiting for busy overlay to disappear")
    
    def expand_all_sections(self) -> None:
        """
        Expand all collapsible sections on the form.
        
        Clicks "Collapse All" then "Expand All" to ensure
        all sections are visible.
        """
        collapse_btn = self._page.locator("#expand-init > span:nth-child(2)")
        collapse_btn.wait_for(state="visible", timeout=self._timeout)
        self.wait_for_obscuring_elements()
        collapse_btn.click()
        self._page.wait_for_timeout(2000)
        
        expand_btn = self._page.locator("#expand-init > span:nth-child(2)")
        expand_btn.wait_for(state="visible", timeout=self._timeout)
        self.wait_for_obscuring_elements()
        expand_btn.click()
        self._page.wait_for_timeout(2000)
    
    def fill_title(self, title: str) -> None:
        """
        Fill the project title field and create the project.
        
        Args:
            title: Project title text
        """
        title_input = self._page.locator("#title")
        title_input.wait_for(state="visible", timeout=self._timeout)
        title_input.fill(title)
        
        save_btn = self._page.locator(".save-project")
        save_btn.wait_for(state="visible", timeout=self._timeout)
        save_btn.click()
        
        continue_btn = self._page.get_by_role("link", name="Continue To Project Workspace")
        continue_btn.wait_for(state="visible", timeout=100000)
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
            if not value or value.strip() == "":
                continue
            
            value = value.strip()
            add_btn = self._page.locator(add_value_selector)
            add_btn.wait_for(state="visible", timeout=100000)
            self.wait_for_obscuring_elements()
            add_btn.click()
            
            agency_tab = self._page.get_by_role("link", name="Organization/Agency")
            agency_tab.wait_for(state="visible", timeout=100000)
            self.wait_for_obscuring_elements()
            agency_tab.click()
            
            org_field = self._page.locator("#orgName")
            org_field.wait_for(state="visible", timeout=100000)
            org_field.fill(value)
            self._page.wait_for_timeout(500)
            
            self._dismiss_autocomplete_dropdown()
            
            self.wait_for_obscuring_elements()
            submit_btn = self._page.locator(".save-org")
            submit_btn.wait_for(state="visible", timeout=100000)
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
        """
        Fill the summary/description field.
        
        Handles the WYSIWYG editor which is inside an iframe.
        
        Args:
            summary: Summary text
        """
        if not summary or summary.strip() == "":
            return
        
        edit_btn = self._page.locator("#edit-dcterms_description_0 > span:nth-child(2)")
        edit_btn.wait_for(state="visible", timeout=100000)
        self.wait_for_obscuring_elements()
        edit_btn.click()
        
        frame = self._page.frame_locator("iframe.wysihtml5-sandbox")
        body = frame.locator("body")
        body.wait_for(state="visible", timeout=100000)
        body.click()
        self._page.wait_for_timeout(300)
        
        body.evaluate(
            """(el, text) => {
                el.textContent = text;
                el.dispatchEvent(new Event('input', { bubbles: true }));
            }""",
            summary,
        )
        self._page.wait_for_timeout(300)
        
        self.wait_for_obscuring_elements()
        save_btn = self._page.locator(".glyphicon-ok").first
        save_btn.wait_for(state="visible", timeout=100000)
        self.wait_for_obscuring_elements()
        save_btn.click()
    
    def fill_original_url(self, url: str) -> None:
        """
        Fill the original distribution URL field.
        
        Args:
            url: Source URL
        """
        if not url or url.strip() == "":
            return
        
        edit_btn = self._page.locator(
            "#edit-imeta_sourceURL_0 > span:nth-child(1) > span:nth-child(2)"
        )
        edit_btn.wait_for(state="visible", timeout=50000)
        self.wait_for_obscuring_elements()
        edit_btn.click()
        
        url_input = self._page.locator(".editable-input > input:nth-child(1)").first
        url_input.wait_for(state="visible", timeout=50000)
        self.wait_for_obscuring_elements()
        url_input.fill(url)
        url_input.press("Enter")
    
    def fill_keywords(self, keywords: List[str]) -> None:
        """
        Fill the subject terms/keywords field.
        
        Uses select2 autocomplete - types each keyword and selects
        the matching suggestion.
        
        Args:
            keywords: List of keywords to add
        """
        for keyword in keywords:
            keyword = keyword.strip(" '")
            if len(keyword) <= 2:
                continue
            
            try:
                self.wait_for_obscuring_elements()
                search_field = self._page.locator(".select2-search__field")
                search_field.wait_for(state="visible", timeout=50000)
                search_field.click()
                search_field.fill(keyword)
                self.wait_for_obscuring_elements()
                
                option = self._page.locator(
                    f"xpath=//li[contains(@class, 'select2-results__option') and text()='{keyword}']"
                )
                option.wait_for(state="visible", timeout=50000)
                self.wait_for_obscuring_elements()
                option.click()
            except PlaywrightTimeoutError as e:
                Logger.warning(f"Could not add keyword '{keyword}': {e}")
    
    def fill_geographic_coverage(self, coverage: str) -> None:
        """
        Fill the geographic coverage field.
        
        Args:
            coverage: Geographic coverage text
        """
        if not coverage or coverage.strip() == "":
            return
        
        edit_btn = self._page.locator(
            "#edit-dcterms_location_0 > span:nth-child(1) > span:nth-child(2)"
        )
        edit_btn.wait_for(state="visible", timeout=50000)
        self.wait_for_obscuring_elements()
        edit_btn.click()
        
        cov_input = self._page.locator(".editable-input > input:nth-child(1)").first
        cov_input.wait_for(state="visible", timeout=50000)
        self.wait_for_obscuring_elements()
        cov_input.fill(coverage)
        cov_input.press("Enter")
    
    def fill_time_period(self, start: Optional[str], end: Optional[str]) -> None:
        """
        Fill the time period fields.
        
        Args:
            start: Start date (YYYY-MM-DD or YYYY-MM or YYYY)
            end: End date (YYYY-MM-DD or YYYY-MM or YYYY)
        """
        if (not start or start.strip() == "") and (not end or end.strip() == ""):
            return
        
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
    
    def fill_data_types(self, data_type: str) -> None:
        """
        Fill the data types field.
        
        Selects the appropriate data type by clicking the span containing the text.
        
        Args:
            data_type: Data type to select (e.g. "geographic information system (GIS) data")
        """
        if not data_type or data_type.strip() == "":
            return
        
        edit_btn = self._page.locator("#disco_kindOfData_0 > span:nth-child(2)")
        edit_btn.wait_for(state="visible", timeout=50000)
        self.wait_for_obscuring_elements()
        edit_btn.click()
        self.wait_for_obscuring_elements()
        
        datatype_span = self._page.locator(
            f"xpath=//span[contains(text(), '{data_type}')]"
        )
        datatype_span.wait_for(state="visible", timeout=50000)
        datatype_span.click()
        
        save_btn = self._page.locator(".editable-submit")
        save_btn.wait_for(state="visible", timeout=50000)
        save_btn.click()
    
    def fill_collection_notes(self, notes: str, download_date: Optional[str] = None) -> None:
        """
        Fill the collection notes field.
        
        Handles the WYSIWYG editor. Optionally appends download date.
        
        Args:
            notes: Collection notes text
            download_date: Optional download date to append as "(Downloaded {date})"
        """
        download_part = f"(Downloaded {download_date})" if download_date else ""
        text = (notes or "").strip()
        if text and download_part:
            combined = f"{text} {download_part}"
        elif download_part:
            combined = download_part
        else:
            return
        
        edit_btn = self._page.locator("#edit-imeta_collectionNotes_0 > span:nth-child(2)")
        edit_btn.wait_for(state="visible", timeout=50000)
        self.wait_for_obscuring_elements()
        edit_btn.click()
        
        frame = self._page.frame_locator("iframe.wysihtml5-sandbox")
        body = frame.locator("body")
        body.wait_for(state="visible", timeout=50000)
        body.click()
        self._page.wait_for_timeout(300)
        
        body.evaluate(
            """(el, text) => {
                el.textContent = text;
                el.dispatchEvent(new Event('input', { bubbles: true }));
            }""",
            combined,
        )
        self._page.wait_for_timeout(300)
        
        self.wait_for_obscuring_elements()
        save_btn = self._page.locator(".editable-submit")
        save_btn.wait_for(state="visible", timeout=50000)
        save_btn.click()
