# Interactive Collector

Standalone tool to fetch URLs and explore links. It runs independently from the DRP Pipeline but reuses pipeline code (URL fetch, 404 and logical-404 detection).

## Phase 1 — Done

- Enter a single URL; the tool fetches the page and displays it.
- Result shows **Status** (OK, 404, or 404 logical) and the response body (or a message for binary/invalid).
- **Logical 404**: same detection as the pipeline (e.g. HTTP 200 with “page not found” style content).

## Phase 2 — Done (current)

- **Three-pane layout**: Scoreboard (left), Source and Linked panes side by side.
- **Scoreboard**: Hierarchical list of visited URLs (by referrer) with status (OK, 404, 404 logical).
- **Follow links**: Links in the page are rewritten so that clicking opens the target in the **Linked** pane and keeps the source page visible in **Source**.
- **Base tag** injection so relative CSS/JS/images load; only `<a href="...">` is rewritten (stylesheets etc. unchanged).

## Phase 3 — Next

- **Persistence**: Optional save/load or clear of scoreboard (or persist to pipeline DB).
- **Export**: Export scoreboard or visited-URL list (e.g. for pipeline input).
- **Pipeline integration**: Feed collected URLs/status into the DRP pipeline.
- **Polish**: Clear scoreboard button, invalid-URL handling in link-click flow, optional back/forward.

## Requirements

- Python 3.13 (or compatible)
- Dependencies from the repo root `requirements.txt` (including `flask`, `requests`)

## Run from repository root

From the DRPPipeline repo root:

```text
python -m interactive_collector
```

Then open **http://127.0.0.1:5000/** in a browser. Use the form to enter a URL and click **Go**. Click links in the Source (or Linked) pane to open them in the Linked pane; the scoreboard shows a tree of visited URLs and 404s.

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

The tool imports from `utils.url_utils` (`is_valid_url`, `fetch_page_body`). Pipeline integration is planned for later.
