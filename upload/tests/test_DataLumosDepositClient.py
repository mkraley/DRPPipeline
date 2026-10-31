"""Unit tests for the deposit client and metadata writer."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from upload.DataLumosDepositClient import DataLumosDepositClient
from upload.DepositMetadata import DepositMetadata
from upload.DepositMetadataWriter import DepositMetadataWriter
from upload.deposit_page_request import AJAX_JS
from upload.tests.deposit_attribute_samples import sample_payload


class TestDataLumosDepositClient(unittest.TestCase):
    """Request shape for create, post, and log redaction."""

    def test_ajax_keeps_the_token_in_the_page(self) -> None:
        """The page script sets the bearer header and does not return the token."""
        self.assertIn("global: false", AJAX_JS)
        self.assertIn("Authorization", AJAX_JS)
        self.assertNotIn("return jwtToken", AJAX_JS)

    def test_create_project_posts_general_type(self) -> None:
        """createProject sends the title and prjType without opening the workspace form."""
        page = MagicMock()
        page.evaluate.return_value = {
            "status": 200,
            "body": json.dumps({"id": 99, "newPath": "/datalumos/99", "action": "create"}),
            "elapsedMs": 5,
        }
        path = DataLumosDepositClient(page).create_project("TRIAL River gauges")
        self.assertEqual(path, "/datalumos/99")
        url = page.evaluate.call_args.args[1]["url"]
        self.assertIn("/createProject?", url)
        self.assertIn("prjType=general", url)
        self.assertIn("TRIAL%20River%20gauges", url)

    def test_failed_call_redacts_token_and_log_omits_query(self) -> None:
        """Errors and the JSONL log do not keep a bearer token or query values."""
        page = MagicMock()
        token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signaturepart"
        page.evaluate.return_value = {"status": 500, "body": token, "elapsedMs": 4}
        with tempfile.TemporaryDirectory() as folder:
            log_path = Path(folder) / "trial.jsonl"
            client = DataLumosDepositClient(page, log_path=log_path)
            with self.assertRaises(RuntimeError) as caught:
                client.post_property("/datalumos/1", "dcterms_description_0", "x", "Summary")
            self.assertNotIn("eyJ", str(caught.exception))
            logged = log_path.read_text(encoding="utf-8-sig")
        self.assertNotIn("eyJ", logged)
        self.assertNotIn("label=", logged)
        self.assertIn("/deposit/postProperty", logged)
        self.assertIn('"at"', logged)

    def test_fill_posts_summary_without_a_second_attribute_load(self) -> None:
        """One getAttributes is followed by the summary post and nothing else."""
        page = MagicMock()
        calls: list[dict[str, object]] = []

        def evaluate(_script: str, request: dict[str, object]) -> dict[str, object]:
            calls.append(request)
            url = str(request["url"])
            if "getAttributes" in url:
                return {"status": 200, "body": json.dumps(sample_payload()), "elapsedMs": 2}
            return {"status": 200, "body": "{}", "elapsedMs": 2}

        page.evaluate.side_effect = evaluate
        metadata = DepositMetadata(
            title="TRIAL",
            agencies=(),
            investigators=(),
            summary="<p>Hello</p>",
            original_url="",
            keywords=(),
            geography=(),
            time_start="",
            time_end="",
            data_types=(),
            notes="",
        )
        DepositMetadataWriter(DataLumosDepositClient(page)).fill_metadata("/datalumos/9", metadata)
        self.assertEqual(len(calls), 2)
        posted = calls[1]
        self.assertEqual(posted["data"]["name"], "dcterms_description_0")
        self.assertEqual(posted["data"]["pk"], "/datalumos/9")
        self.assertEqual(posted["data"]["value"], "<p>Hello</p>")

    def test_missing_attribute_names_the_labels_that_were_returned(self) -> None:
        """A field with a value and no attribute stops instead of clicking the form."""
        page = MagicMock()
        summary_only = {
            "allSections": [
                {
                    "groups": [
                        {
                            "attributes": [
                                {
                                    "resourceProperty": {
                                        "label": "Summary",
                                        "ontology": "dcterms",
                                        "attribute": "description",
                                        "uiControl": "wysihtml5",
                                        "type": "",
                                        "value": "",
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        page.evaluate.return_value = {
            "status": 200,
            "body": json.dumps(summary_only),
            "elapsedMs": 1,
        }
        metadata = DepositMetadata(
            title="TRIAL",
            agencies=("EPA",),
            investigators=(),
            summary="",
            original_url="",
            keywords=(),
            geography=(),
            time_start="",
            time_end="",
            data_types=(),
            notes="",
        )
        with self.assertRaises(RuntimeError) as caught:
            DepositMetadataWriter(DataLumosDepositClient(page)).fill_metadata("/datalumos/9", metadata)
        self.assertIn("No deposit attribute for agency", str(caught.exception))
        self.assertIn("Summary", str(caught.exception))

    def test_unlisted_subject_term_is_posted_as_entered(self) -> None:
        """A term missing from suggestSubjectTerms is still posted, as a select2 tag."""
        page = MagicMock()
        calls: list[dict[str, object]] = []

        def evaluate(_script: str, request: dict[str, object]) -> dict[str, object]:
            calls.append(request)
            url = str(request["url"])
            if "getAttributes" in url:
                return {"status": 200, "body": json.dumps(sample_payload()), "elapsedMs": 1}
            if "suggestSubjectTerms" in url and "public" in url:
                return {"status": 200, "body": json.dumps(["Public health"]), "elapsedMs": 1}
            if "suggestSubjectTerms" in url:
                return {"status": 200, "body": "[]", "elapsedMs": 1}
            return {"status": 200, "body": "{}", "elapsedMs": 1}

        page.evaluate.side_effect = evaluate
        metadata = DepositMetadata(
            title="TRIAL",
            agencies=(),
            investigators=(),
            summary="",
            original_url="",
            keywords=("public health", "categorical evaluation"),
            geography=(),
            time_start="",
            time_end="",
            data_types=(),
            notes="",
        )
        DepositMetadataWriter(DataLumosDepositClient(page)).fill_metadata("/datalumos/9", metadata)
        posted = next(call for call in calls if "postProperty" in str(call["url"]))
        self.assertEqual(
            posted["data"]["value"],
            "Public health~~categorical evaluation~~",
        )


if __name__ == "__main__":
    unittest.main()
