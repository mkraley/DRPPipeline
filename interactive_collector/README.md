# Interactive Collector

Standalone tool to fetch URLs and explore links. It runs independently from the DRP Pipeline but reuses pipeline code (URL fetch, 404 and logical-404 detection).

## Phase 1 (current)

- Enter a single URL; the tool fetches the page and displays it.
- Result page shows **Status** (OK, 404, or 404 logical), **Content-Type**, and the response body.
- **Logical 404**: same detection as the pipeline (e.g. HTTP 200 with “page not found” style content).

Later phases will add: clickable links in the page, a second pane for linked pages, and a hierarchical scoreboard of visited URLs and 404s.

## Requirements

- Python 3.13 (or compatible)
- Dependencies from the repo root `requirements.txt` (including `flask`, `requests`)

## Run from repository root

From the DRPPipeline repo root:

```text
python -m interactive_collector
```

Then open **http://127.0.0.1:5000/** in a browser. Use the form to enter a URL and click **Fetch**.

## Running tests

From the repo root:

```text
python -m pytest interactive_collector\tests -v
```

Or run the whole project test suite; `utils.tests.test_url_utils` includes tests for the shared `fetch_page_body` and `body_looks_like_not_found` used by the collector.

## Project layout

- `app.py` — Flask app and single route (form + fetch result).
- `__main__.py` — Entrypoint for `python -m interactive_collector`.
- `tests/` — Unit tests for the app and helpers.

The tool imports from `utils.url_utils` (`is_valid_url`, `fetch_page_body`). Pipeline integration is planned for later.
