# Interactive Collector

Standalone tool to fetch URLs and explore links. It reuses pipeline code (URL fetch, 404 and logical-404 detection) and can be driven by the DRP Pipeline from the database (first eligible project with prereq=sourcing, no errors).

## Phase 1 — Done

- Enter a single URL; the tool fetches the page and displays it.
- Result shows **Status** (OK, 404, or 404 logical) and the response body (or a message for binary/invalid).
- **Logical 404**: same detection as the pipeline (e.g. HTTP 200 with “page not found” style content).

## Phase 2 — Done (current)

- **Three-pane layout**: Scoreboard (left), Source and Linked panes side by side.
- **Scoreboard**: Hierarchical list of visited URLs (by referrer) with status (OK, 404, 404 logical).
- **Follow links**: Links in the page are rewritten so that clicking opens the target in the **Linked** pane and keeps the source page visible in **Source**.
- **Base tag** injection so relative CSS/JS/images load; only `<a href="...">` is rewritten (stylesheets etc. unchanged).
- **Saving non-HTML links**: PDF, CSV, ZIP, XML, and other non-HTML resources show a download button to save to the project folder. Uses `utils.url_utils.is_non_html_response` (magic bytes, Content-Type, body sniffing) consistently across SPA and legacy app.

## Pipeline integration — Done

- **DB-driven**: The app uses the pipeline database (Storage) when available. On first load with no URL, it asks Storage for the first eligible project (prereq=sourcing, no errors) and populates the Source pane and **DRPID** in the top bar.
- **Next**: When a project is loaded, a **Next** button appears; it fetches the next eligible project (by DRPID) and loads it.
- **Load by DRPID**: Enter a DRPID in the **Load DRPID** field and click **Load** to fetch that project’s record and load its source URL.
- **Run from orchestrator**: Use module `interactive_collector`. The orchestrator sets the app’s DB path (same as pipeline) and starts the Flask app; the app then loads the first eligible project from Storage. No environment variables are used.
- **Standalone**: Run `python -m interactive_collector`; the app uses `drp_pipeline.db` in the current directory by default. If there are no eligible projects, the form is shown with no DRPID.

## Phase 3 — Done

- **Clear scoreboard**: Button to clear the scoreboard (API: POST /api/scoreboard/clear).
- **Export**: Export scoreboard as JSON or visited URLs as CSV (for pipeline input).
- **Pipeline integration**: On save, visited URLs and status are written to Storage `status_notes`.
- **Polish**: Clear scoreboard button.

## Phase 4 — Next

- **Persistence**: Optional save/load of scoreboard (or persist to pipeline DB).
- **Invalid-URL handling**: Handle invalid URLs in link-click flow.
- **Optional back/forward**: Browser-like back/forward in panes.

## Requirements

- Python 3.13 (or compatible)
- Dependencies from the repo root `requirements.txt` (including `flask`, `requests`)

## Run from repository root

**Standalone (form-driven):**

From the DRPPipeline repo root:

```text
python -m interactive_collector
```

Then open **http://127.0.0.1:5000/** in a browser. Use the form to enter a URL and click **Go**. Click links in the Source (or Linked) pane to open them in the Linked pane; the scoreboard shows a tree of visited URLs and 404s.

**Pipeline-driven (DB-driven):**

From the repo root, run the pipeline with module `interactive_collector` (same DB and args as other modules):

```text
python main.py --module interactive_collector [--db-path drp_pipeline.db]
```

The orchestrator finds the first project eligible for collection (prereq=sourcing, no errors), sets the initial URL and DRPID, and starts the app. Open **http://127.0.0.1:5000/**; the Source pane shows that project’s URL and the top bar shows **DRPID: &lt;id&gt;**.

## Running tests

From the repo root:

```text
python -m pytest interactive_collector\tests -v
```

Or run the whole project test suite; `utils.tests.test_url_utils` includes tests for the shared `fetch_page_body` and `body_looks_like_not_found` used by the collector.

## Project layout

- `app.py` — Flask app (single route: form, scoreboard, Source/Linked panes; link rewriting and base injection).
- `__main__.py` — Entrypoint for `python -m interactive_collector`.
- `tests/` — Unit tests for the app and helpers.

The tool imports from `utils.url_utils` (`is_valid_url`, `fetch_page_body`) and uses `storage.Storage` to read the pipeline DB (first/next eligible, load by DRPID). The orchestrator sets `app.config["DRP_DB_PATH"]` so the app uses the same database.
