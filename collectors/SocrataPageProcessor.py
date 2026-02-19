"""
Socrata Page Processor for DRP Pipeline.

Handles preprocessing of Socrata pages:
- Expanding "read more" links
- Setting pagination to show all rows
- Generating PDF from the page
"""

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from utils.Errors import record_error, record_warning
from utils.Logger import Logger

if TYPE_CHECKING:
    from collectors.SocrataCollector import SocrataCollector


class SocrataPageProcessor:
    """
    Processes Socrata pages: expands content and generates PDF.
    
    Handles the preprocessing steps needed before PDF generation:
    - Expanding "read more" sections
    - Setting pagination to show all rows
    - Generating PDF output
    """
    
    def __init__(self, collector: "SocrataCollector") -> None:
        """
        Initialize SocrataPageProcessor with a SocrataCollector instance.
        
        Args:
            collector: SocrataCollector instance to access page and result
        """
        self._collector = collector
    
    def generate_pdf(self, pdf_path: Path) -> bool:
        """
        Process page (expand content, show all rows) and generate PDF.
        
        Performs all preprocessing steps before generating the PDF.
        Updates result directly on success.
        
        Args:
            pdf_path: Path where PDF should be saved
            
        Returns:
            True if PDF was generated successfully, False otherwise
        """
        # Get total rows
        total_rows = self._get_total_rows()
        if total_rows:
            Logger.debug(f"Total columns in dataset: {total_rows}")
        
        # Show all rows
        self._show_all_rows(total_rows)
        
        # Expand read more links and hide the buttons
        self._expand_read_more_links()
        
        # Generate PDF
        success = self._generate_pdf(pdf_path)
        if success:
            Logger.debug(f"PDF generated: {pdf_path}")
        else:
            record_error(self._collector._drpid, "PDF generation failed")
            Logger.warning("PDF generation failed")
        
        return success
    
    def _get_total_rows(self) -> Optional[int]:
        """
        Get the total number of rows from the paginator legend (e.g., "1-15 of 125" -> 125) that lists the columns in the dataset.
        
        Returns:
            Total number of rows, or None if not found
        """
        try:
            # Playwright can pierce shadow DOM with locator, but for complex shadow DOM
            # operations like accessing slots, we use a minimal evaluate call
            result = self._collector._page.evaluate("""
                () => {
                    try {
                        const fp = document.querySelector('forge-paginator');
                        if (!fp || !fp.shadowRoot) return null;
                        
                        const rangeLabel = fp.shadowRoot.querySelector('.range-label');
                        if (!rangeLabel) return null;
                        
                        let rangeText = (rangeLabel.textContent || rangeLabel.innerText || '').trim();
                        const slot = rangeLabel.querySelector('slot[name="range-label"]');
                        if (slot && slot.assignedNodes) {
                            const assigned = slot.assignedNodes();
                            if (assigned.length > 0) {
                                rangeText = assigned.map(n => n.textContent || '').join(' ').trim();
                            }
                        }
                        
                        const match = rangeText.match(/of\\s+(\\d+)/i);
                        return match ? parseInt(match[1]) : null;
                    } catch (e) {
                        return null;
                    }
                }
            """)
            return result
        except Exception:
            return None
    
    def _show_all_rows(self, total_rows: Optional[int]) -> bool:
        """
        Set the paginator for the list of columns in the dataset to show all rows.
        
        Args:
            total_rows: Total number of rows (if known)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            target_page_size = total_rows if total_rows and total_rows > 100 else 100
            
            rows_result = self._collector._page.evaluate(f"""
                () => {{
                    try {{
                        const fp = document.querySelector('forge-paginator');
                        if (!fp) {{
                            return {{ success: false, message: 'forge-paginator not found' }};
                        }}
                        
                        const fs = fp.shadowRoot.querySelector('forge-select');
                        if (!fs) {{
                            return {{ success: false, message: 'forge-select not found' }};
                        }}
                        
                        const targetSize = {target_page_size};
                        
                        if (targetSize > 100) {{
                            const option100 = fs.querySelector('forge-option[label="100"]');
                            if (option100) {{
                                option100.setAttribute('label', targetSize.toString());
                                option100.textContent = targetSize.toString();
                            }}
                        }}
                        
                        fs.value = targetSize.toString();
                        fp.pageSize = targetSize;
                        
                        const changeEvent = new Event('change', {{ bubbles: true, cancelable: true }});
                        fs.dispatchEvent(changeEvent);
                        
                        const paginatorChangeEvent = new CustomEvent('forge-paginator-change', {{
                            bubbles: true,
                            cancelable: true,
                            detail: {{
                                type: 'page-size',
                                pageSize: targetSize,
                                pageIndex: fp.pageIndex || 0,
                                offset: fp.offset || 0
                            }}
                        }});
                        fp.dispatchEvent(paginatorChangeEvent);
                        
                        return {{ success: true, message: 'Set to ' + targetSize }};
                    }} catch (e) {{
                        return {{ success: false, message: 'Error: ' + e.message }};
                    }}
                }}
            """)
            
            if rows_result and rows_result.get('success'):
                self._collector._page.wait_for_timeout(2000)
                return True
            else:
                # Fallback to 100
                fallback_result = self._collector._page.evaluate("""
                    () => {
                        try {
                            const fp = document.querySelector('forge-paginator');
                            if (!fp) return { success: false };
                            
                            const fs = fp.shadowRoot.querySelector('forge-select');
                            if (!fs) return { success: false };
                            
                            fs.value = '100';
                            fp.pageSize = 100;
                            
                            const changeEvent = new Event('change', { bubbles: true, cancelable: true });
                            fs.dispatchEvent(changeEvent);
                            
                            return { success: true };
                        } catch (e) {
                            return { success: false };
                        }
                    }
                """)
                self._collector._page.wait_for_timeout(2000)
                return fallback_result.get('success', False)
        except Exception as e:
            Logger.warning(f"Could not change rows per page: {e}")
            return False
    
    def _expand_read_more_links(self) -> int:
        """
        Find and click "Read more" links/buttons to expand content.
        After expanding, hides the forge-button.collapse-button elements.
        
        Returns:
            Number of links clicked
        """
        try:
            buttons = self._collector._page.locator('forge-button.collapse-button')
            button_count = buttons.count()
            
            max_clicks = min(button_count, 100)
            clicked_count = 0
            
            for i in range(max_clicks):
                try:
                    buttons.nth(i).click(timeout=1000)
                    clicked_count += 1
                except Exception:
                    continue
            
            if clicked_count > 0:
                self._collector._page.wait_for_timeout(1500)
                Logger.debug(f"Expanded {clicked_count} 'Read more' sections")
                
                # Hide the collapse buttons after expanding
                self._hide_collapse_buttons()
            
            return clicked_count
        except Exception as e:
            Logger.warning(f"Could not expand 'Read more' links: {e}")
            return 0
    
    def _hide_collapse_buttons(self) -> None:
        """
        Remove the forge-button.collapse-button elements from the DOM.
        """
        try:
            self._collector._page.evaluate("""
                () => {
                    const buttons = document.querySelectorAll('forge-button.collapse-button');
                    Array.from(buttons).forEach(button => button.remove());
                }
            """)
        except Exception as e:
            Logger.debug(f"Could not remove collapse buttons: {e}")
    
    _PDF_TIMEOUT_MS = 90000

    def _generate_pdf(self, pdf_path: Path) -> bool:
        """
        Generate PDF from the current page.
        
        Sets a generous timeout so print doesn't hang silently, and injects
        print CSS to reduce layout issues (borders/overlap) in Chromium print.
        
        Args:
            pdf_path: Path where PDF should be saved
            
        Returns:
            True if successful, False otherwise
        """
        page = self._collector._page
        try:
            page.set_default_timeout(self._PDF_TIMEOUT_MS)
            page.add_style_tag(
                content="""
                @media print {
                    * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
                    table, tr, .card, [role="row"] { break-inside: avoid; }
                }
                """
            )
            page.pdf(path=str(pdf_path), format="A4", print_background=True)
            return True
        except Exception as e:
            Logger.error(f"Failed to generate PDF: {e}")
            return False
