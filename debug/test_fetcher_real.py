"""
Test SpreadsheetCandidateFetcher against the real Google Sheets database.

Sets num_rows=10 and fetches candidate URLs from the actual Data_Inventories spreadsheet.
"""

import sys
from pathlib import Path

# Add parent directory to path so we can import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sourcing.SpreadsheetCandidateFetcher import SpreadsheetCandidateFetcher
from utils.Args import Args
from utils.Logger import Logger


def main() -> None:
    """Test fetcher with real spreadsheet, num_rows=10."""
    # Initialize Args and Logger
    Args.initialize()
    Logger.initialize(log_level="INFO")
    
    # Set num_rows to 10
    Args._config["sourcing_num_rows"] = 10
    
    Logger.info("Testing SpreadsheetCandidateFetcher with real spreadsheet...")
    Logger.info(f"Spreadsheet URL: {Args.sourcing_spreadsheet_url}")
    Logger.info(f"URL column: {Args.sourcing_url_column}")
    Logger.info(f"Num rows limit: {Args.sourcing_num_rows}")
    Logger.info("")
    
    try:
        fetcher = SpreadsheetCandidateFetcher()
        urls = fetcher.get_candidate_urls()
        
        Logger.info(f"Successfully fetched {len(urls)} candidate URLs (limit: {Args.sourcing_num_rows})")
        Logger.info("")
        Logger.info("URLs:")
        for i, url in enumerate(urls, 1):
            Logger.info(f"  {i}. {url}")
        
        if len(urls) < Args.sourcing_num_rows:
            Logger.info("")
            Logger.info(f"Note: Only {len(urls)} URLs found (less than limit of {Args.sourcing_num_rows})")
        
    except Exception as e:
        Logger.error(f"Error fetching candidate URLs: {e}")
        raise


if __name__ == "__main__":
    main()
