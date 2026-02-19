# HTML-to-PDF conversion

The pipeline uses **Playwright (headless Chromium)** to turn web pages into PDFs in two places:

- **Interactive collector Save**: checked scoreboard URLs are loaded and printed to PDF in the project folder.
- **Socrata collector**: after collecting a Socrata page, the same browser page is printed to PDF (with optional pre-processing like “show all rows”, expand “Read more”).

## Current behavior and limits

- **Navigation**: We use `wait_until="domcontentloaded"` (not `networkidle`) so JS-heavy or long‑lived network pages (e.g. Socrata, datadiscovery) don’t wait forever. A short settle delay and a generous print timeout are applied.
- **Timeouts**: If something still hangs, the default timeout (e.g. 90s) should fire and an **ERROR** line is emitted in the save progress stream; check the UI/log for that message.
- **Layout**: Chromium’s print engine can misplace borders or overlap text on complex CSS (flex/grid, shadows). We inject print CSS (`print-color-adjust: exact`, `break-inside: avoid` on tables/cards) to reduce some of that; it won’t fix every site.

## Alternative techniques (if you need them)

If Playwright continues to time out or layout is unacceptable, you can consider:

| Approach | Pros | Cons |
|----------|------|------|
| **WeasyPrint** (Python) | Good for static HTML/CSS, no browser, predictable layout, CSS Paged Media. | Does **not** run JavaScript; only suitable for HTML you already have (e.g. fetched and saved). Not for Socrata/datadiscovery live pages. |
| **wkhtmltopdf** | Single binary, often faster than full browser, decent layout for many pages. | Uses older WebKit; some modern JS/CSS may not render; requires installing the binary. |
| **Chrome/Chromium CLI** | `--headless --print-to-pdf=out.pdf`; same engine as Playwright. | Same layout/timeout issues; you’d need to drive it yourself (subprocess or script). |
| **Puppeteer** | Same as Playwright (Chromium); different API. | Same behavior; no clear advantage unless you’re already in a Node stack. |

For **JS-heavy or live Socrata/datadiscovery pages**, a headless browser (Playwright or similar) is still the only option; the improvements above aim to make that path more reliable and visible when it fails.
