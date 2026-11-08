# DataLumos deposit API

The DataLumos workspace is a front end for the ICPSR deposit service. Upload, publish, and in-progress cleanup call that service directly. The browser is still used to sign in and to hold the session. These are the calls the pipeline makes, taken from the workspace page and from `deposit.min.js` build 20260910-150211. ICPSR has not published this as a stable API, and the workspace JavaScript contains other calls the pipeline does not use.

Base URL: `https://deposit.icpsr.umich.edu/deposit`

A project is a path `/datalumos/{id}`, where `{id}` is the numeric DataLumos id (`datalumos_id` in the database). The tenant and archive are both `datalumos`.

## Authentication

Sign-in is still the DataLumos / Keycloak page in a headed browser. After login, the workspace HTML contains an inline assignment:

```javascript
var jwtToken = "...";
```

The pipeline reads that value from the workspace document (or from the page once a script has assigned it) and sends it on later calls:

```http
Authorization: Bearer {jwtToken}
```

The browser cookie jar goes with the request. File uploads copy those cookies onto a separate HTTP client because the body is a streamed multipart file. A `401` drops the saved token so the next project signs in again. Tokens are not written to the log.

The same token is reused for every project in a batch. The workspace is opened again only when the page has no token, which happens after a fresh login and after the GWDA nomination leaves the browser on another site.

## Create a project

`POST /deposit/createProject?newProject={json}&prjType=general`

`newProject` is a JSON object, encoded as one query value:

| Field | Value |
|-------|--------|
| `resourceUri` | `/datalumos` |
| `tenant` | `datalumos` |
| `archive` | `datalumos` |
| `displayName` | Project title, already truncated the way the form truncates it |

A successful body includes `newPath` (`/datalumos/{id}`). When `newPath` is absent and `id` is present, the path is `/datalumos/{id}`.

## Read project metadata

`GET /deposit/getAttributes?pathUrl={path}&tenant=datalumos&level=project`

`path` is `/datalumos/{id}`. The body is a tree of sections and groups. Each editable field is a `resourceProperty`:

| Field | Role |
|-------|------|
| `label` | Text shown on the form |
| `ontology` | Prefix such as `dcterms`, `imeta`, `disco`, `icpsr` |
| `attribute` | Name within that ontology |
| `uiControl` | Widget: `text`, `wysihtml5`, `keyword`, `checklist`, `timePeriod`, and others |
| `type` | `list` when the form adds values one at a time |
| `value` | Current value |

The wire name of a field is `{ontology}_{attribute}`. The pipeline loads this list once per project and posts each field without loading it again.

Labels the uploader looks for, and the keys it uses when the label text changes:

| Pipeline field | Form label | Key when present |
|----------------|------------|------------------|
| Summary | Summary, Description, Project description | `dcterms_description` |
| Original URL | Alternative URL, Original URL, Source URL, Distribution URL | `imeta_sourceURL` |
| Collection notes | Collection notes, Notes | `imeta_collectionNotes` |
| Kind of data | Data type, Data types, Kind of data | `disco_kindOfData` |
| Geographic coverage | Geographic coverage | `dcterms_location` |
| Subject terms | Subject Terms, or a `keyword` control | |
| Time period | Time Period, or a `timePeriod` control | |
| Agency | Government Agency, Organization/Agency, Agency | |
| Investigators | Principal Investigator(s) | |

## Write one field

`POST /deposit/postProperty?label={label}`

`label` is the form label. The value is a form body, not a query parameter:

| Form field | Value |
|------------|--------|
| `name` | Field id, below |
| `pk` | `/datalumos/{id}` |
| `value` | The text to store |

`name` is `{ontology}_{attribute}_{hash}`. `hash` is the Java `String.hashCode` of the current value. An empty field hashes to `0`, so a first write of summary is `dcterms_description_0`.

List fields (geographic coverage) use a new slot per entry: `{ontology}_{attribute}_XX{hash}`, where the hash is of the 1-based index as a string.

Several values in one property are joined with a trailing `~~` on each value: `alpha~~beta~~`. Kind of data uses the checklist's lowercase wire labels (`survey data`, `aggregate data`, and the other labels on the form). Subject terms are one `~~`-joined property after each term is checked against the thesaurus.

## Organizations, people, and dates

These are separate from `postProperty`. `name` is the attribute key (`ontology_attribute`), not the hashed data id.

`POST /deposit/addOrg?path={path}&name={key}&orgName={agency}`

One call per agency or office.

`POST /deposit/addPerson?path={path}&name={key}&personFirstName={first}&personLastName={last}&personName={first last}&personOrgName={affiliation}`

`personOrgName` is omitted when there is no affiliation. One call per investigator.

`POST /deposit/addDateRange?path={path}&startDate={start}&endDate={end}&label={control}`

`label` is the attribute's `uiControl`, or `timePeriod` when that is empty. Used for the project time period. A time period without a start date is refused locally and is not posted.

## Subject-term suggestions

`GET /deposit/suggestSubjectTerms?term={text}&page=1`

Returns the thesaurus hits for one keyword. A suggestion whose text matches the keyword (ignoring case) is stored with the thesaurus spelling. A keyword with no match is stored as typed. The form's subject-term control allows terms that are not in the list.

## Upload files

These are the requests behind the Upload button and Import From Zip. The project page is not opened.

`POST /deposit/uploadRawFile?resourceId=/datalumos/{id}&lastModified={ms}&type={mime}`

Multipart body, field name `file`, original filename. `lastModified` is the file's modification time in milliseconds. `type` is the MIME type guessed from the filename, or `application/octet-stream`. Up to four files are posted at once.

A 2xx body that is a JSON object is success when `fileStatus` is absent or empty. `{"name": "notes.txt"}` is the usual queued body. `fileStatus: "failed"` is a rejection and uses `description` as the message. Any other `fileStatus` is also a rejection. An empty 200 body means the file is already in the project.

`POST /deposit/uploadZipFile?resourceId=/datalumos/{id}&lastModified={ms}&type={mime}`

Same request shape. Used when the project folder contains subfolders: the folder is zipped and posted once. A body with `"type": "zip"` is success.

## Storage inventory

`GET /deposit/viewStorage?path={path}`

Publish reads this before it will publish. The fields the pipeline uses:

| Field | Meaning |
|-------|---------|
| `fileFolderUsed` | File and folder count shown as Storage Status |
| `storageUsedDisplay` | Space label, such as `1.2 GB` or `< 0.01 GB` |

The count must equal `num_files` plus the number of product folders. The space label must match `file_size`. A label like `< 0.01 GB` matches any database size under that threshold.

## Publish

Publish Data posts the object returned by the terms call, with the review-dialog answers filled in. The four reads happen first, in this order:

| Call | Query |
|------|--------|
| `GET /deposit/getTermsAndConditions` | `resourcePath={path}&type=project` |
| `GET /deposit/getReviewTerms` | `resourcePath={path}` |
| `GET /deposit/getTermsAttributes` | `path={path}` |
| `GET /deposit/licenseList` | `path={path}` |

`getTermsAttributes` says which questions this project shows. `licenseList` is a list of `{id, name}`. Public Domain Mark is the entry whose name contains "public domain", or id `15` when the list has that id and no matching name.

`POST /deposit/publish`

JSON body is the `getTermsAndConditions` object with these fields set:

| Field | Value |
|-------|--------|
| `disclosureRisk` | `"false"` |
| `sensitiveDataRisk` | `false` |
| `publicAccess` | `true` |
| `delayedDissemination` | `false` |
| `delayedDisseminationDateStr` | `null` |
| `delayedDisseminationDate` | `null` |
| `agreed` | `true` |
| `licenseId` | Public Domain Mark id, as a string |
| `reviewTerms` | The `getReviewTerms` payload, unchanged |
| `accessible` | The WCAG attestation string, only when the terms include `accessibleQuestion` |
| `versionTitle` | Republish note, only when republishing |

The POST can return before the public page exists. The pipeline then opens `https://www.datalumos.org/datalumos/project/{id}/version/V1/view` in the browser, up to 18 times about 5 seconds apart. That page is the public website, not a deposit call. It counts as published when the response is HTTP 200, the URL is not a login or Cloudflare challenge, and the HTML contains `Published Versions`.

## Delete a draft

`DELETE /deposit/deletePath?path={path}`

`path` is `/datalumos/{id}` for a whole project. Cleanup of Deposit In Progress uses this. A 2xx body that still contains `errorCode` is a rejection. Published projects come back that way (`errorMessage` such as a cannot-delete-published message). `errorCode` is the fallback text when `errorMessage` is missing.

## What stays in the browser

Sign-in, the deposit token, and the public-view check are browser steps. GWDA nomination is a separate site (`https://digital2.library.unt.edu/nomination/GWDA-US-2025/add/`) and runs before the deposit calls. `--ui-upload` uses the workspace form for project creation and metadata, and the project-page file modal for files. Publish uses the deposit calls above either way.
