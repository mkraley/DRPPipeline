# Publisher Module – Implementation Plan

## Overview

Add a **publisher** module that completes the DataLumos workflow by performing the “publish” step after upload. Projects with `status="upload"` will be published in DataLumos; the module will capture the public URL and update Storage with `published_url` and `status="publisher"`.

The implementation will follow the same pattern as the **upload** module: Playwright-based browser automation, implementing `ModuleProtocol`, with logic derived from the Selenium version in **chiara_upload.py** (`C:\Documents\Code\CDCDataCollector\chiara_upload.py`; see `publish_workspace()`). Convert all Selenium calls to Playwright.

---

## Prerequisites / Reference

- **chiara_upload.py** (Selenium): `C:\Documents\Code\CDCDataCollector\chiara_upload.py`. The publish flow is in `publish_workspace()` (lines 746–868). Use it as the reference for selectors, order of steps, retry logic, and error checks.
- **Upload module** (Playwright): Use as the structural and style template:
  - `DataLumosUploader` (orchestration, browser lifecycle, `run(drpid)`)
  - `DataLumosAuthenticator`, `DataLumosFormFiller`, `DataLumosFileUploader` (focused helpers)
  - Reuse auth and browser setup patterns; publisher will need to open the same DataLumos project page and perform publish-specific actions.

---

## 1. Scope

| Item | Description |
|------|-------------|
| **Input** | Projects with `status="upload"` and valid `datalumos_id` (and no errors). |
| **Output** | For each project: set `published_url` (from DataLumos after publish), set `status="publisher"`. |
| **Failure** | On error: append to project `errors`, do not update status; log and continue batch as per existing pipeline behavior. |

---

## 2. Module Layout

Mirror the upload package layout:

```
publisher/
  __init__.py
  DataLumosPublisher.py      # Main class: ModuleProtocol, run(drpid), browser lifecycle
  (optional) DataLumosPublishFlow.py  # Optional helper: publish button, modals, URL capture
  tests/
    __init__.py
    test_DataLumosPublisher.py
    (test_DataLumosPublishFlow.py if helper exists)
```

- **One class per file**, filename = class name in snake_case (per `.cursorrules`).
- Keep files under ~200 lines; split into a “flow” helper if the main class grows large.

---

## 3. DataLumosPublisher (main class)

- **Implements**: `ModuleProtocol` (implement `run(self, drpid: int) -> None`).
- **Responsibilities**:
  - Get project from `Storage.get(drpid)`; validate `datalumos_id` and `status` (or rely on orchestrator giving only `status="upload"`).
  - Start Playwright browser (reuse same pattern as `DataLumosUploader`: chromium, viewport, user agent, timeouts).
  - Authenticate with DataLumos (reuse `DataLumosAuthenticator` from upload module).
  - Navigate to project page using `datalumos_id` (same URL pattern as upload: workspace project URL).
  - Run the publish flow (see below); capture `published_url`.
  - On success: `Storage.update_record(drpid, {"published_url": published_url, "status": "publisher"})`.
  - On failure: `record_error(drpid, message)` and optionally append to project errors; do not change status to `"publisher"`.
  - Close browser in a `finally` block (same as upload).
- **Config**: Reuse `Args.upload_timeout`, `Args.upload_headless`, `Args.datalumos_username`, `Args.datalumos_password`. No new Args required for the first iteration unless we later need a separate publisher timeout.

---

## 4. Publish Flow (from chiara_upload.py → Playwright)

Source: `C:\Documents\Code\CDCDataCollector\chiara_upload.py`, function `publish_workspace()` (lines 746–868). Convert each Selenium step to Playwright as below. Chiara uses **retry logic**: try twice; on first failure wait 5 seconds and retry once.

### Step-by-step mapping (Selenium → Playwright)

| Step | chiara_upload.py (Selenium) | Playwright equivalent |
|------|-----------------------------|-------------------------|
| 0 | Wait for busy overlay | Same as upload: `#busy` hidden (reuse `DataLumosFormFiller.wait_for_obscuring_elements` or inline `page.locator("#busy").first.wait_for(state="hidden")`). |
| 1 | Click “Publish Project” | `By.XPATH, "//button[contains(@class, 'btn-primary') and contains(., 'Publish Project')]"` → `page.get_by_role("button", name="Publish Project")` or `page.locator("button.btn-primary:has-text('Publish Project')")`. |
| 2 | Wait for review page | `'reviewPublish' in d.current_url` → `page.wait_for_url("**/reviewPublish**", timeout=30000)` or poll until `"reviewPublish" in page.url`. |
| 2b | Error check | If timeout: look for `#errormsg` with text → `page.locator("#errormsg")`; if visible and has text, treat as error and retry or fail. |
| 3 | Click “Proceed to Publish” | `//button[contains(@class, 'btn-primary') and contains(., 'Proceed to Publish')]` → `page.locator("button.btn-primary:has-text('Proceed to Publish')").click()`. |
| 4 | Dialog: noDisclosure | `By.ID, "noDisclosure"` → `page.locator("#noDisclosure").click()`. |
| 5 | Dialog: sensitiveNo | `By.ID, "sensitiveNo"` → `page.locator("#sensitiveNo").click()`. |
| 6 | Dialog: depositAgree | `By.ID, "depositAgree"` → `page.locator("#depositAgree").click()`. |
| 7 | Click “Publish Data” | `//button[contains(., 'Publish Data')]` → `page.locator("button.btn-primary:has-text('Publish Data')").click()`. |
| 8 | Click “Back to Project” | `//button[contains(., 'Back to Project')]` → `page.locator("button.btn-primary:has-text('Back to Project')").click()`. |
| 9 | Wait back at workspace | URL contains `/datalumos/` and not `reviewPublish` → wait for URL or state. |
| 10 | Error check | `#errormsg` with text → same as 2b; if present, fail/retry. |

### published_url

Chiara does **not** read a “published URL” from the page. In `update_google_sheet()` it sets **Download Location** to:

`https://www.datalumos.org/datalumos/project/{workspace_id}/version/V1/view`

So for the publisher module, set:

`published_url = f"https://www.datalumos.org/datalumos/project/{workspace_id}/version/V1/view"`

using the project’s existing `datalumos_id` (workspace_id). No need to scrape the page for a link.

### Implementation options

- **Option A**: Implement all steps inside `DataLumosPublisher` (e.g. in `_publish_project()`), keeping one file.
- **Option B**: Extract the flow into a helper class (e.g. `DataLumosPublishFlow`) that takes a `Page` and runs the steps; returns success/failure. Keeps `DataLumosPublisher` under ~200 lines.

Recommendation: Start with Option A; refactor to Option B if the main class grows too large or you want isolated tests for the flow with a mocked Page.

---

## 5. Orchestration and CLI

- **Orchestrator** (`orchestration/Orchestrator.py`):
  - Add to `MODULES`:
    - `"publisher": { "prereq": "upload", "class_name": "DataLumosPublisher" }`
  - No other orchestrator logic changes (it already discovers classes by name and runs `run(drpid)` for each eligible project).
- **Args** (`utils/Args.py`):
  - Update the `module` argument help string to include `publisher`, e.g.  
    `"Module to run: noop, sourcing, collector, upload, publisher"` (or current list + publisher).

---

## 6. Storage

- **Read**: `Storage.get(drpid)` for project; require `datalumos_id` (and optionally `folder_path` if needed for any publish step).
- **Write**: `Storage.update_record(drpid, {"published_url": str, "status": "publisher"})` on success.
- **Schema**: `published_url` and `status` already exist in `StorageSQLLite`; no schema change.

---

## 7. Testing

- **test_DataLumosPublisher.py** (in `publisher/tests/`):
  - Mock `Storage.get` / `Storage.update_record` and `record_error`.
  - Mock Playwright (e.g. `sync_playwright`, `Page`, `Browser`, etc.) so that `run(drpid)` does not open a real browser.
  - Test: eligible project → `run(drpid)` → `Storage.update_record` called with `status="publisher"` and non-empty `published_url`.
  - Test: missing `datalumos_id` → error recorded, no status update.
  - Test: browser/publish failure → error recorded, no status update.
  - Test: `close()` is safe when browser was never started or already closed.
- If a helper class exists: add `test_DataLumosPublishFlow.py` with a mocked `Page` and assert correct locator clicks and URL extraction.

Follow existing patterns in `upload/tests/` (e.g. `test_DataLumosUploader.py`, `test_DataLumosAuthenticator.py`) for mocks and structure.

---

## 8. Checklist (per .cursorrules)

- [ ] Unit tests in `publisher/tests/test_DataLumosPublisher.py` (and helper tests if added).
- [ ] Type hints on all function signatures.
- [ ] Docstrings on all public functions and classes.
- [ ] Methods short, single responsibility; files under ~200 lines where possible.
- [ ] No duplication: reuse auth and browser setup from upload; reuse `wait_for_obscuring_elements`-style logic if applicable.
- [ ] UTF-8-sig for any new CSV/text outputs; Windows path syntax where paths are used.
- [ ] Logging: use `Logger.info` / `Logger.warning` / `Logger.error` / `Logger.exception` as in upload.
- [ ] README.md updated to mention the publisher module and the `publisher` CLI option.
- [ ] requirements.txt already includes Playwright; no change unless a new dependency is added.
- [ ] At the end: provide `git add` and `git commit` for all changed/added files.

---

## 9. Implementation Order

1. **Add publisher package**: `publisher/__init__.py`, `publisher/DataLumosPublisher.py` with minimal `run(drpid)` (load project, validate, stub publish that sets `published_url` from workspace ID template).
2. **Register module**: Orchestrator `MODULES` + Args help text.
3. **Implement browser + auth**: Reuse Playwright and `DataLumosAuthenticator`; navigate to project by `datalumos_id` (same workspace URL pattern as upload).
4. **Implement publish flow**: Implement Section 4 steps in Playwright (Publish Project → reviewPublish → Proceed to Publish → noDisclosure / sensitiveNo / depositAgree → Publish Data → Back to Project); retry once after 5 s on failure; check `#errormsg` on timeout/after steps; set `published_url` from template.
5. **Add tests**: Mocks for Storage and Playwright; assert success and failure paths.
6. **Polish**: Logging, error messages, README, and final git commit.

---

## 10. Optional Later Enhancements

- Separate `publisher_timeout` / `publisher_headless` in Args if operations need different timeouts or visibility.
- Retry logic for transient failures (e.g. network) during publish.
- “Update master spreadsheet” (from Thoughts on restructuring) can remain a separate step or future module once publisher is stable.
