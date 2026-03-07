# DRP Pipeline — Setup

This document covers prerequisites and installation. For configuration and usage, see [Usage](Usage.md).

## Prerequisites

- Python 3.13 or later
- pip (Python package manager)

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd DRPPipeline
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Install Playwright browsers (required for web scraping and DataLumos automation):
   ```bash
   playwright install
   ```

## Browser extension (optional)

The browser extension lets you browse source pages in a real browser and save pages as PDF to the interactive collector when AWS WAF blocks automated access.

### Extension installation

1. Open Chrome and go to `chrome://extensions`.
2. Enable **Developer mode** (toggle in the top right).
3. Click **Load unpacked**.
4. Select the `interactive_collector/extension` folder in this project.
5. The extension is now loaded.

### Extension usage

1. Start the collector (Flask app) and load a project with a source URL.
2. In the collector, click **Copy & Open** next to the source URL.
3. Open the extended browser (the same Chrome where the extension is installed).
4. Paste the copied URL into the address bar and press Enter.
5. The launcher page loads briefly, stores the project ID, then redirects to the source URL.
6. Browse the site. When you find a page to save, click **Save as PDF** (floating button in the bottom-right corner).
7. The PDF is sent to the collector and added to the scoreboard.
8. In the collector window, click **Refresh** on the scoreboard to see the new entry.

**PDF quality:** The extension uses html2pdf/html2canvas. Cross-origin images load via the collector's `/api/proxy`. Wait for the page and lazy images to load before saving.
