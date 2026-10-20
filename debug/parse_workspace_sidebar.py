"""Extract unpublished DataLumos ids from a saved sidebar transcript."""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cleanup_inprogress.workspace_list import project_url, unpublished_workspace_ids


def _sidebar_html(transcript: Path) -> str:
    """Return the pasted sidebar HTML from a chat transcript."""
    for line in transcript.read_text(encoding="utf-8").splitlines():
        if "list-group" not in line:
            continue
        record = json.loads(line)
        content = record.get("message", {}).get("content", [])
        if not content:
            continue
        text = content[0].get("text", "")
        start = text.find("<ul")
        end = text.rfind("</ul>")
        if start >= 0 and end > start:
            return text[start : end + len("</ul>")]
    return ""


def main() -> int:
    """Write unpublished project ids and direct URLs to a CSV."""
    transcript = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    html = _sidebar_html(transcript)
    if not html:
        print("sidebar html not found", file=sys.stderr)
        return 1
    ids = unpublished_workspace_ids(html)
    out_path.parent.mkdir(exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["workspace_id", "url"])
        for workspace_id in ids:
            writer.writerow([workspace_id, project_url(workspace_id)])
    print(f"count={len(ids)}")
    print(f"first={ids[0] if ids else ''}")
    print(f"last={ids[-1] if ids else ''}")
    print(f"wrote={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
