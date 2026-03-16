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

## Browser extension (optional - used by the interactive_collector)

The browser extension lets you browse source pages in a real browser and save pages as PDF to the interactive collector when AWS WAF blocks automated access.

### Extension installation

1. Open Chrome and go to `chrome://extensions`.
2. Enable **Developer mode** (toggle in the top right).
3. Click **Load unpacked**.
4. Select the `interactive_collector/extension` folder in this project.
5. The extension is now loaded.
6. If the extension code is updated, make sure the version number in manifest.json is bumped. Then navigate to `chrome://extensions` and click the circular arrow to reload the code.


