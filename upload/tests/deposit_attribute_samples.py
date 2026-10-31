"""Shared getAttributes payloads for deposit client tests."""

from __future__ import annotations

from typing import Any

from upload.DepositAttribute import DepositAttribute, flatten_attributes


def sample_payload() -> dict[str, Any]:
    """Return a small getAttributes document covering the upload fields."""
    return {
        "allSections": [
            {
                "groups": [
                    {
                        "attributes": [
                            _property("Summary", "dcterms", "description", "wysihtml5"),
                            _property("Subject Terms", "icpsr", "subject", "keyword"),
                            _property("Government Agency", "icpsr", "agency", "text"),
                            _property("Principal Investigator(s)", "icpsr", "pi", "text"),
                            _property("Geographic coverage", "dcterms", "location", "text", "list"),
                            _property("Time Period", "dcterms", "temporal", "timePeriod"),
                            _property("Data type", "disco", "kindOfData", "checklist"),
                            _property("Collection notes", "imeta", "collectionNotes", "wysihtml5"),
                            _property("Alternative URL", "imeta", "sourceURL", "text"),
                        ]
                    }
                ]
            }
        ]
    }


def sample_attributes() -> list[DepositAttribute]:
    """Return the flattened sample attributes."""
    return flatten_attributes(sample_payload())


def _property(
    label: str,
    ontology: str,
    attribute: str,
    ui_control: str,
    type_name: str = "",
) -> dict[str, Any]:
    """Build one resourceProperty wrapper."""
    return {
        "resourceProperty": {
            "label": label,
            "ontology": ontology,
            "attribute": attribute,
            "uiControl": ui_control,
            "type": type_name,
            "value": "",
        }
    }
