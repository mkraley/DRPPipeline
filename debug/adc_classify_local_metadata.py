"""Classify file hosting from local adc_metadata.json (no API calls)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sourcing.AdcFileInventory import AdcFileInventory


def raw_pattern(files: list[dict]) -> str:
    """Label the Figshare files array before resolution."""
    if not files:
        return "no_files"
    if len(files) > 1:
        return "figshare_multi"
    only = files[0]
    size = int(only.get("size") or 0)
    url = str(only.get("download_url") or "")
    if size > 0:
        return "figshare_hosted"
    if "doi.org" in url:
        if "dryad" in url or "10.5061" in url:
            return "doi_placeholder_dryad"
        if "zenodo" in url or "10.5281" in url:
            return "doi_placeholder_zenodo"
        return "doi_placeholder_other"
    if only.get("is_link_only"):
        return "link_only_external"
    return "zero_byte_other"


def main(root: Path) -> None:
    """Scan collected metadata folders and summarize hosting patterns."""
    inventory = AdcFileInventory()
    raw_counts: dict[str, int] = {}
    resolved_counts: dict[str, int] = {}
    examples: dict[str, tuple[str, str]] = {}

    paths = sorted(root.glob("DRP*/adc_metadata.json"))
    for meta_path in paths:
        article = json.loads(meta_path.read_text(encoding="utf-8"))
        files = article.get("files") or []
        pattern = raw_pattern(files)
        raw_counts[pattern] = raw_counts.get(pattern, 0) + 1
        hosting = inventory.classify_hosting(article)
        resolved_counts[hosting] = resolved_counts.get(hosting, 0) + 1
        if pattern not in examples:
            title = str(article.get("title") or "")[:50]
            detail = ""
            if len(files) == 1:
                detail = str(files[0].get("download_url") or "")[:70]
            examples[pattern] = (meta_path.parent.name, f"{title} | {detail}")

    print(f"Scanned {len(paths)} local adc_metadata.json files under {root}\n")
    print("Raw Figshare file patterns:")
    for key, count in sorted(raw_counts.items(), key=lambda item: -item[1]):
        drp, note = examples.get(key, ("?", ""))
        print(f"  {key:24} {count:3d}   e.g. {drp}: {note}")

    print("\nAfter AdcFileInventory resolution (classify_hosting):")
    for key, count in sorted(resolved_counts.items(), key=lambda item: -item[1]):
        print(f"  {key:24} {count:3d}")

    print("\nCollector outcome for key patterns:")
    print("  figshare_hosted / figshare_multi -> auto download via Figshare")
    print("  doi_placeholder_dryad/zenodo   -> external-unresolved TODAY (manual); API exists but not wired for USDA.ADC DOI articles")
    print("  link_only_external               -> download attempted; often fails (DRP 15)")


if __name__ == "__main__":
    data_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"C:\DataRescue\ADCData")
    main(data_root)
