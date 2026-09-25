"""
Load ICPSR Subject Thesaurus preferred terms.

Source list: https://www.icpsr.umich.edu/web/ICPSR/thesaurus/10001
Built by copying preferred labels into data/icpsr_subject_thesaurus.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_THESAURUS_PATH = REPO_ROOT / "data" / "icpsr_subject_thesaurus.json"


class IcpsrSubjectThesaurus:
    """In-memory set of ICPSR subject preferred terms."""

    def __init__(self, terms: list[dict[str, Any]]) -> None:
        """Index preferred labels. Aliases are ignored; only preferred terms may be assigned."""
        self.preferred_terms: set[str] = set()
        for entry in terms:
            preferred = str(entry.get("preferred") or "").strip()
            if preferred:
                self.preferred_terms.add(preferred)

    @classmethod
    def load(cls, path: Path | None = None) -> IcpsrSubjectThesaurus:
        """Load a thesaurus JSON file. Defaults to data/icpsr_subject_thesaurus.json."""
        thesaurus_path = path or DEFAULT_THESAURUS_PATH
        data = json.loads(thesaurus_path.read_text(encoding="utf-8"))
        return cls(data["terms"])

    def contains(self, term: str) -> bool:
        """Return True when term is a preferred label in this thesaurus."""
        return term in self.preferred_terms
