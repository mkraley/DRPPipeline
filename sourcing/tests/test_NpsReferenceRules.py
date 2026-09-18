"""Tests for IRMA URL, nesting, and public-file helpers."""

from __future__ import annotations

import unittest

from sourcing.NpsReferenceRules import (
    as_reference_dicts,
    irma_project_id_from_source_url,
    is_public_downloadable_product,
    is_public_digital_file,
    product_public_file_count,
    profile_children,
    project_direct_public_file_count,
    reference_id_of,
    reference_profile_url,
)


class TestNpsReferenceRules(unittest.TestCase):
    """Tests for NPS IRMA reference helpers."""

    def test_profile_url_round_trip(self) -> None:
        """Build and parse IRMA Profile URLs."""
        url = reference_profile_url(2268446)
        self.assertEqual(
            url,
            "https://irma.nps.gov/DataStore/Reference/Profile/2268446",
        )
        self.assertEqual(irma_project_id_from_source_url(url), 2268446)
        self.assertIsNone(irma_project_id_from_source_url("https://example.com/Profile/1"))

    def test_as_reference_dicts_flattens_nested_project_object(self) -> None:
        """Nested ``{project: [...]}`` payloads unwrap to reference dicts."""
        rows = as_reference_dicts(
            {"project": [{"reference": {"referenceId": 9, "title": "X"}}]}
        )
        self.assertEqual(rows[0]["referenceId"], 9)

    def test_profile_children_prefers_children_list(self) -> None:
        """Program children come from the children array when present."""
        children = profile_children(
            {
                "children": [{"referenceId": 1, "referenceType": "Project"}],
                "projects": {"project": [{"referenceId": 2}]},
            }
        )
        self.assertEqual(reference_id_of(children[0]), 1)

    def test_public_digital_file_requires_url_and_type(self) -> None:
        """External Links and files without URLs are skipped."""
        self.assertTrue(
            is_public_digital_file(
                {"resourceType": "Digital File", "url": "https://example/file.zip"}
            )
        )
        self.assertFalse(
            is_public_digital_file(
                {"resourceType": "External Link", "url": "https://example"}
            )
        )
        self.assertFalse(
            is_public_digital_file({"resourceType": "Digital File", "url": ""})
        )

    def test_project_direct_files_require_public_visibility(self) -> None:
        """Internal projects do not count attached Digital Files."""
        files = [{"resourceType": "Digital File", "url": "https://x/a.zip"}]
        self.assertEqual(
            project_direct_public_file_count({"visibility": "Public", "filesAndLinks": files}),
            1,
        )
        self.assertEqual(
            project_direct_public_file_count({"visibility": "Internal", "filesAndLinks": files}),
            0,
        )

    def test_public_downloadable_product(self) -> None:
        """Restricted or internal products are not collectible."""
        public = {
            "fileCount": 2,
            "fileAccess": "Public",
            "visibility": "Public",
        }
        self.assertTrue(is_public_downloadable_product(public))
        self.assertEqual(product_public_file_count(public), 2)
        self.assertEqual(
            product_public_file_count(
                {"fileCount": 2, "fileAccess": "Restricted", "visibility": "Public"}
            ),
            0,
        )

    def test_public_digital_files_skips_external_links(self) -> None:
        """External Links are omitted from the downloadable file list."""
        from sourcing.NpsReferenceRules import public_digital_files

        files = public_digital_files(
            {
                "visibility": "Public",
                "filesAndLinks": [
                    {"resourceType": "Digital File", "url": "https://x/a.csv", "fileName": "a.csv"},
                    {"resourceType": "External Link", "url": "https://example.com"},
                ],
            }
        )
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["fileName"], "a.csv")


if __name__ == "__main__":
    unittest.main()
