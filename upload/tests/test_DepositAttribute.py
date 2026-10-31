"""Unit tests for deposit attribute parsing and field ids."""

from __future__ import annotations

import unittest

from upload.DepositAttribute import (
    checklist_wire_value,
    flatten_attributes,
    java_string_hash,
    list_slot_id,
    scalar_data_id,
)
from upload.deposit_field_match import match_fields, suggestion_texts
from upload.tests.deposit_attribute_samples import sample_attributes, sample_payload


class TestDepositAttribute(unittest.TestCase):
    """Hash, flatten, and checklist wire values."""

    def test_empty_string_hash_is_zero(self) -> None:
        """An empty value uses the same suffix the workspace shows as ``_0``."""
        self.assertEqual(java_string_hash(""), 0)

    def test_hash_of_one_matches_deposit_script(self) -> None:
        """``"1".hashCode()`` in deposit.js is 49, the first add-value slot."""
        self.assertEqual(java_string_hash("1"), 49)

    def test_scalar_id_for_empty_description(self) -> None:
        """Empty summary posts to ``dcterms_description_0``."""
        attrs = match_fields(flatten_attributes(sample_payload()))
        self.assertEqual(scalar_data_id(attrs["summary"]), "dcterms_description_0")

    def test_list_slot_uses_xx_prefix(self) -> None:
        """The first added list value uses the ``_XX`` id from deposit.js."""
        attrs = match_fields(flatten_attributes(sample_payload()))
        self.assertEqual(list_slot_id(attrs["geography"], 1), "dcterms_location_XX49")

    def test_flatten_reads_nested_resource_properties(self) -> None:
        """Properties nested under sections and groups are collected once."""
        attrs = flatten_attributes(sample_payload())
        self.assertIn("dcterms_description", {attr.key for attr in attrs})

    def test_checklist_keeps_gis_capitals(self) -> None:
        """The GIS checklist value keeps the abbreviation capitalized."""
        wire = checklist_wire_value("Geographic information system (GIS) data")
        self.assertEqual(wire, "geographic information system (GIS) data")

    def test_suggestion_texts_accept_strings_and_objects(self) -> None:
        """Suggestion bodies may be a list of strings or objects."""
        self.assertEqual(suggestion_texts(["Health"]), ["Health"])
        self.assertEqual(suggestion_texts({"results": [{"text": "Health"}]}), ["Health"])

    def test_match_fields_uses_labels_when_keys_differ(self) -> None:
        """Agency and investigators are found from their labels."""
        matched = match_fields(sample_attributes())
        self.assertEqual(matched["agency"].label, "Government Agency")
        self.assertEqual(matched["investigators"].key, "icpsr_pi")
        self.assertEqual(matched["keywords"].ui_control, "keyword")


if __name__ == "__main__":
    unittest.main()
