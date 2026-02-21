# DRP Collector Browser Extension Setup

The browser extension lets you browse catalog.data.gov (and other data.gov sites) in a real browser and save pages as PDF to the collector when AWS WAF blocks automated access.

## Installation

1. Open Chrome and go to `chrome://extensions`.
2. Enable **Developer mode** (toggle in the top right).
3. Click **Load unpacked**.
4. Select the `interactive_collector/extension` folder in this project.
5. The extension is now loaded.

## Usage

1. Start the collector (Flask app) and load a project with a source URL.
2. In the collector, click **Copy & Open** next to the source URL.
3. Open the extended browser (the same Chrome where the extension is installed).
4. Paste the copied URL into the address bar and press Enter.
5. The launcher page loads briefly, stores the project ID, then redirects to the source URL.
6. Browse the site. When you find a page to save, click **Save as PDF** (floating button in the bottom-right corner).
7. The PDF is sent to the collector and added to the scoreboard.
8. In the collector window, click **Refresh** on the scoreboard to see the new entry.

## PDF quality (CSS and images)

The extension uses html2pdf, which renders the page with html2canvas. For best results:

- **Images**: Cross-origin images are loaded via the collector’s `/api/proxy`, which avoids CORS issues. The collector must be running when you click **Save as PDF**.
- **CSS**: html2canvas uses the browser’s computed styles, so visible styles should appear in the PDF. If styles are missing, they may be applied late or via Shadow DOM, which can limit fidelity.
- **Headed mode**: The extension runs in your normal Chrome session (headed). Headed vs headless is not the cause of missing CSS/images.
- **Fully loaded page**: Wait until the page and any lazy images have loaded before saving.
