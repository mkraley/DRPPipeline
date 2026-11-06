"""Tests for the DataLumos publish request body."""

from __future__ import annotations

import unittest

from publisher.publish_terms import (
    PUBLIC_DOMAIN_LICENSE_ID,
    apply_publish_answers,
    public_domain_license_id,
    term_attribute_names,
)


class TestPublishTerms(unittest.TestCase):
    """Publish Data posts the same answers the terms dialog used to click."""

    def test_answers_match_the_terms_dialog(self) -> None:
        """Disclosure, sensitivity, access, embargo, license, and agreement are fixed."""
        body = apply_publish_answers(
            {"projectTitle": "Study", "disclosureRisk": "true"},
            {"depositAgreement": "text"},
            {"licenseQuestion"},
            PUBLIC_DOMAIN_LICENSE_ID,
        )
        self.assertEqual(body["disclosureRisk"], "false")
        self.assertIs(body["sensitiveDataRisk"], False)
        self.assertIs(body["publicAccess"], True)
        self.assertIs(body["delayedDissemination"], False)
        self.assertIsNone(body["delayedDisseminationDate"])
        self.assertIs(body["agreed"], True)
        self.assertEqual(body["licenseId"], "15")
        self.assertEqual(body["reviewTerms"]["depositAgreement"], "text")
        self.assertNotIn("accessible", body)
        self.assertNotIn("versionTitle", body)

    def test_accessible_attestation_is_included_only_when_asked(self) -> None:
        """The ADA sentence is sent only when terms attributes include that question."""
        body = apply_publish_answers(
            {},
            {},
            {"accessibleQuestion"},
            "15",
            version_title="added missing file",
        )
        self.assertTrue(str(body["accessible"]).startswith("Yes."))
        self.assertEqual(body["versionTitle"], "added missing file")

    def test_public_domain_is_chosen_by_name(self) -> None:
        """A license whose name says public domain wins over a hard-coded id."""
        license_id = public_domain_license_id(
            [{"id": 9, "name": "CC0"}, {"id": 22, "name": "Public Domain Mark"}]
        )
        self.assertEqual(license_id, "22")

    def test_attribute_names_walk_nested_groups(self) -> None:
        """Question names are collected from nested attribute objects."""
        names = term_attribute_names(
            [{"groups": [{"attributes": [{"attribute": "licenseQuestion"}]}]}]
        )
        self.assertEqual(names, {"licenseQuestion"})


if __name__ == "__main__":
    unittest.main()
