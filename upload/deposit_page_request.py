"""
Browser-side request helpers for the DataLumos deposit API.

The page script attaches the session bearer token and does not return it.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

DEPOSIT_SERVER = "https://deposit.icpsr.umich.edu/deposit"
WORKSPACE_URL = "https://www.datalumos.org/datalumos/workspace"
HOME_PATH = "/datalumos"

_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")

AJAX_JS = """async (request) => {
  const started = performance.now();
  const result = await new Promise((resolve) => {
    $.ajax({
      url: request.url,
      type: request.method,
      data: request.data || undefined,
      contentType: request.contentType || undefined,
      dataType: "text",
      global: false,
      crossDomain: true,
      timeout: 120000,
      beforeSend: (xhr) => {
        if (typeof jwtToken === "string" && jwtToken) {
          xhr.setRequestHeader("Authorization", "Bearer " + jwtToken);
        }
      },
      success: (data, _status, xhr) => {
        resolve({status: xhr.status, body: data == null ? "" : String(data)});
      },
      error: (xhr) => {
        resolve({status: xhr.status || 0, body: xhr.responseText || ""});
      },
    });
  });
  return {
    status: result.status,
    body: result.body,
    elapsedMs: Math.round(performance.now() - started),
  };
}"""


def redact_secrets(text: str) -> str:
    """Replace bearer-token shaped text so logs and errors stay shareable."""
    return _JWT_RE.sub("[redacted-jwt]", text)


def encode_query(value: str) -> str:
    """Encode one query value the way ``encodeURIComponent`` does."""
    return quote(value, safe="-_.!~*'()")


def append_deposit_log(
    log_path: Path | None,
    method: str,
    url: str,
    status: int,
    elapsed_ms: Any,
    body_text: str,
) -> None:
    """Append one redacted request summary. Query values are omitted."""
    append_deposit_record(
        log_path,
        {
            "method": method,
            "path": urlsplit(url).path,
            "status": status,
            "elapsedMs": elapsed_ms,
            "responseBytes": len(body_text.encode("utf-8")),
        },
    )


def append_deposit_record(log_path: Path | None, record: dict[str, Any]) -> None:
    """Append one JSON object with a local timestamp. Query values are omitted."""
    if log_path is None:
        return
    stamped = {"at": datetime.now().astimezone().isoformat(timespec="seconds"), **record}
    log_path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not log_path.exists()
    line = json.dumps(stamped, ensure_ascii=False) + "\n"
    with log_path.open("a", encoding="utf-8") as handle:
        if new_file:
            handle.write("\ufeff")
        handle.write(line)
