"""
Attribute records from the DataLumos deposit ``getAttributes`` response.

Field identity is ``ontology_attribute``. Empty scalar values use the same
Java-style hash the deposit page appends, which is ``0`` for an empty string.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator


@dataclass(frozen=True)
class DepositAttribute:
    """One editable metadata attribute on a deposit project."""

    label: str
    ontology: str
    attribute: str
    ui_control: str
    type_name: str
    value: Any
    multiple: bool

    @property
    def key(self) -> str:
        """Return the ``ontology_attribute`` name the deposit API expects."""
        return f"{self.ontology}_{self.attribute}"


_CHECKLIST_WIRE: dict[str, str] = {
    "Administrative records data": "administrative records data",
    "Aggregate data": "aggregate data",
    "Experimental data": "experimental data",
    "Geographic information system (GIS) data": (
        "geographic information system (GIS) data"
    ),
    "Observational data": "observational data",
    "Program source code": "program source code",
    "Survey data": "survey data",
}


def java_string_hash(value: str) -> int:
    """Return the 32-bit hash used by ``String.prototype.hashCode`` in deposit.js."""
    hashed = 0
    for character in value:
        hashed = ((hashed << 5) - hashed + ord(character)) & 0xFFFFFFFF
        if hashed >= 0x80000000:
            hashed -= 0x100000000
    return hashed


def scalar_data_id(attr: DepositAttribute) -> str:
    """Return the data id for a single-value attribute, including an empty one."""
    current = "" if attr.value is None else str(attr.value)
    return f"{attr.key}_{java_string_hash(current)}"


def list_slot_id(attr: DepositAttribute, index: int) -> str:
    """Return the data id the add-value control creates for a new list entry."""
    return f"{attr.key}_XX{java_string_hash(str(index))}"


def tilde_join(values: list[str]) -> str:
    """Join values the way checklist and subject-term posts do, with a trailing marker."""
    return "".join(f"{value}~~" for value in values)


def checklist_wire_value(label: str) -> str:
    """Map a DataLumos checklist label to the value the deposit page posts."""
    return _CHECKLIST_WIRE.get(label, label)


def flatten_attributes(payload: Any) -> list[DepositAttribute]:
    """Collect ``resourceProperty`` objects from a getAttributes payload."""
    found: list[DepositAttribute] = []
    seen: set[int] = set()
    for raw in _walk_properties(payload, seen):
        ontology = str(raw.get("ontology") or "").strip()
        attribute = str(raw.get("attribute") or "").strip()
        if not ontology or not attribute:
            continue
        found.append(
            DepositAttribute(
                label=str(raw.get("label") or "").strip(),
                ontology=ontology,
                attribute=attribute,
                ui_control=str(raw.get("uiControl") or "").strip(),
                type_name=str(raw.get("type") or "").strip(),
                value=raw.get("value"),
                multiple=bool(raw.get("multiple")),
            )
        )
    return found


def _walk_properties(node: Any, seen: set[int]) -> Iterator[dict[str, Any]]:
    """Yield each resourceProperty dict once."""
    if isinstance(node, dict):
        raw = node.get("resourceProperty")
        if isinstance(raw, dict) and id(raw) not in seen:
            if "attribute" in raw and "ontology" in raw:
                seen.add(id(raw))
                yield raw
        for value in node.values():
            yield from _walk_properties(value, seen)
        return
    if isinstance(node, list):
        for item in node:
            yield from _walk_properties(item, seen)
