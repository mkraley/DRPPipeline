"""
Socrata Metadata Extractor for DRP Pipeline.

Handles extraction of metadata from Socrata pages:
- Extracting title
- Extracting dataset metadata (rows, columns)
- Extracting description text (with rich text)
- Extracting keywords/tags
"""

from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from collectors.SocrataCollector import SocrataCollector


class SocrataMetadataExtractor:
    """
    Extracts metadata from Socrata pages.
    
    Handles:
    - Metadata extraction (title, rows, columns, description, keywords)
    """
    
    def __init__(self, collector: "SocrataCollector") -> None:
        """
        Initialize SocrataMetadataExtractor with a SocrataCollector instance.
        
        Args:
            collector: SocrataCollector instance to access page and result
        """
        self._collector = collector
    
    def extract_all_metadata(self) -> dict:
        """
        Extract all available metadata from the page.
        
        Updates collector result with Storage field names: title, summary, keywords.
        
        Returns:
            Dictionary with keys: title, summary, keywords (and rows, columns for callers).
        """
        title = self._extract_title()
        rows, columns = self._extract_dataset_metadata()
        description = self._extract_description()
        keywords = self._extract_keywords()

        if title is not None:
            self._collector._result["title"] = title
        if description is not None:
            self._collector._result["summary"] = description
        if keywords is not None:
            self._collector._result["keywords"] = keywords

        return {
            "title": title,
            "rows": rows,
            "columns": columns,
            "description": description,
            "keywords": keywords,
        }
    
    def _extract_title(self) -> Optional[str]:
        """
        Extract title from h2.asset-name element.
        
        There should only be one such element.
        
        Returns:
            Title text as string, or None if not found
        """
        try:
            title_locator = self._collector._page.locator('h2.asset-name')
            if title_locator.count() == 0:
                return None
            text = title_locator.first.inner_text()
            return text.strip() if text else None
        except Exception:
            return None
    
    def _extract_dataset_metadata(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract dataset metadata (rows and columns) from the metadata-row element.
        
        Returns:
            Tuple of (rows: str or None, columns: str or None)
        """
        try:
            metadata_row = self._collector._page.locator('dl.metadata-row')
            if metadata_row.count() == 0:
                return None, None
            
            rows = None
            columns = None
            
            pairs = metadata_row.locator('.metadata-pair')
            pair_count = pairs.count()
            
            for i in range(pair_count):
                pair = pairs.nth(i)
                key_locator = pair.locator('.metadata-pair-key')
                value_locator = pair.locator('.metadata-pair-value')
                
                if key_locator.count() == 0 or value_locator.count() == 0:
                    continue
                
                key_text = key_locator.first.inner_text().strip()
                value_text = value_locator.first.inner_text().strip()
                
                if key_text == 'Rows':
                    rows = value_text
                elif key_text == 'Columns':
                    columns = value_text
            
            return rows, columns
        except Exception:
            return None, None
    
    def _extract_description(self) -> Optional[str]:
        """
        Extract description HTML from div.description-section element.
        
        Uses innerHTML to preserve rich text formatting.
        
        Returns:
            Description HTML as string, or None if not found
        """
        try:
            description_locator = self._collector._page.locator('div.description-section')
            if description_locator.count() == 0:
                return None
            html = description_locator.first.inner_html()
            return html.strip() if html else None
        except Exception:
            return None
    
    def _extract_keywords(self) -> Optional[str]:
        """
        Extract keywords from the metadata table.
        
        Looks for div.metadata-table with h3 child "Topics", then finds tr with
        first td "Tags" and extracts textContent from the second td.
        
        Returns:
            Keywords text as string, or None if not found
        """
        try:
            metadata_tables = self._collector._page.locator('div.metadata-table')
            table_count = metadata_tables.count()
            
            for i in range(table_count):
                table = metadata_tables.nth(i)
                h3 = table.locator('> h3').first
                if h3.count() == 0:
                    continue
                
                h3_text = h3.inner_text().strip()
                if h3_text != 'Topics':
                    continue
                
                # Find tr whose first td has text "Tags"
                rows = table.locator('tr')
                row_count = rows.count()
                
                for j in range(row_count):
                    row = rows.nth(j)
                    tds = row.locator('td')
                    if tds.count() < 2:
                        continue
                    
                    first_td_text = tds.nth(0).inner_text().strip()
                    if first_td_text == 'Tags':
                        keywords = tds.nth(1).inner_text().strip()
                        return keywords if keywords else None
            
            return None
        except Exception:
            return None
