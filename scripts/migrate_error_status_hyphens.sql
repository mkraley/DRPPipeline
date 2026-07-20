-- Normalize spaced error statuses to compact xxx-error form.
-- Run against a DRP pipeline database, e.g.:
--   sqlite3 adc.db < scripts/migrate_error_status_hyphens.sql
--
-- Examples rewritten:
--   'sourced - error'              -> 'sourced-error'
--   'uploaded - large file - error'-> 'uploaded-large-file-error'
--   'uploaded - large file-error'  -> 'uploaded-large-file-error'
-- Bare 'error' is left unchanged.

UPDATE projects
SET status = REPLACE(REPLACE(TRIM(status), ' - ', '-'), ' ', '-')
WHERE status LIKE '%error%'
  AND status != 'error'
  AND (
    status LIKE '% - %'
    OR status LIKE '% %'
  );
