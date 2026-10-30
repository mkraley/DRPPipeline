"""GET Energy Star download URLs with longer timeouts (browser-like)."""

from __future__ import annotations

import time
import urllib.request
from pathlib import Path

URLS = [
    "https://data.energystar.gov/api/v3/views/8wj2-sec8/query.xml?accessType=DOWNLOAD",
    "https://data.energystar.gov/api/v3/views/8wj2-sec8/export.csv?accessType=DOWNLOAD",
]


def main() -> None:
    """Stream GET responses and report bytes/timing."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
    }
    out = Path("debug/epa81_downloads")
    out.mkdir(exist_ok=True)
    for url in URLS:
        name = url.split("/")[-1].split("?")[0]
        dest = out / name
        print(f"GET {url}")
        started = time.time()
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                print(
                    " status",
                    resp.status,
                    "ct",
                    resp.headers.get("Content-Type"),
                    "cl",
                    resp.headers.get("Content-Length"),
                    "cd",
                    resp.headers.get("Content-Disposition"),
                )
                total = 0
                with dest.open("wb") as handle:
                    while True:
                        chunk = resp.read(64 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                        total += len(chunk)
                        if total and total % (1024 * 1024) < 64 * 1024:
                            print(f"  ... {total} bytes after {time.time()-started:.1f}s")
            print(f" DONE {total} bytes in {time.time()-started:.1f}s -> {dest}")
        except Exception as exc:  # noqa: BLE001
            print(f" FAIL after {time.time()-started:.1f}s: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
