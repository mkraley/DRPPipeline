"""Tests for skipping metadata that a previous upload already stored."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from utils.Logger import Logger

from upload.DepositAttribute import flatten_attributes
from upload.DepositMetadata import DepositMetadata
from upload.DepositMetadataWriter import DepositMetadataWriter
from upload.deposit_existing import organization_present, person_present, time_period_present
from upload.tests.deposit_attribute_samples import sample_payload


class TestDepositExisting(unittest.TestCase):
    """Stored values are recognized across the shapes getAttributes returns."""

    def test_organization_matches_one_stored_name(self) -> None:
        """The same agency text is present. A different office is not."""
        value = [{"orgName": "Environmental Protection Agency"}]
        self.assertTrue(organization_present(value, "Environmental Protection Agency"))
        self.assertFalse(organization_present(value, "Office of Water"))

    def test_person_matches_first_and_last_in_one_entry(self) -> None:
        """A stored person is not treated as present because of another entry."""
        value = [
            {"personFirstName": "Ada", "personLastName": "Lovelace"},
            {"personFirstName": "Grace", "personLastName": "Hopper"},
        ]
        self.assertTrue(person_present(value, "Ada", "Lovelace"))
        self.assertFalse(person_present(value, "Ada", "Hopper"))

    def test_time_period_matches_a_display_string(self) -> None:
        """A US date range is the same period as the stored ISO dates."""
        value = ["4/2/2019 – 11/13/2026"]
        self.assertTrue(time_period_present(value, "2019-04-02", "2026-11-13"))
        self.assertFalse(time_period_present(value, "2018-01-01", "2018-12-31"))

    def test_time_period_matches_a_year_range(self) -> None:
        """A year-only range is the same period as the years we would post."""
        value = ["2019 – 2026"]
        self.assertTrue(time_period_present(value, "2019", "2026"))
        self.assertFalse(time_period_present(value, "2018", "2019"))


class TestDepositMetadataWriterSkips(unittest.TestCase):
    """A second upload does not append people or periods that are already stored."""

    def setUp(self) -> None:
        """Logger is required when an existing value is skipped."""
        Logger.initialize(log_level="ERROR", log_file=False)

    def test_existing_person_and_period_are_not_posted_again(self) -> None:
        """addPerson and addDateRange are skipped when getAttributes already has them."""
        payload = sample_payload()
        properties = payload["allSections"][0]["groups"][0]["attributes"]
        for wrapper in properties:
            prop = wrapper["resourceProperty"]
            if prop["label"] == "Principal Investigator(s)":
                prop["value"] = [{"personFirstName": "Ada", "personLastName": "Lovelace"}]
            if prop["label"] == "Time Period":
                prop["value"] = [{"startDate": "2019-04-02", "endDate": "2026-11-13"}]
            if prop["label"] == "Government Agency":
                prop["value"] = [{"orgName": "Environmental Protection Agency"}]
        client = MagicMock()
        client.get_attributes.return_value = flatten_attributes(payload)
        metadata = DepositMetadata(
            title="Cattle",
            agencies=("Environmental Protection Agency",),
            investigators=(("Ada", "Lovelace", ""),),
            summary="",
            original_url="",
            keywords=(),
            geography=(),
            time_start="2019-04-02",
            time_end="2026-11-13",
            data_types=(),
            notes="",
        )
        DepositMetadataWriter(client).fill_metadata("/datalumos/9", metadata)
        client.add_organization.assert_not_called()
        client.add_person.assert_not_called()
        client.add_date_range.assert_not_called()

    def test_empty_fields_are_still_posted(self) -> None:
        """A project with no stored person or period still receives both."""
        client = MagicMock()
        client.get_attributes.return_value = flatten_attributes(sample_payload())
        metadata = DepositMetadata(
            title="Cattle",
            agencies=("Environmental Protection Agency",),
            investigators=(("Ada", "Lovelace", "EPA"),),
            summary="",
            original_url="",
            keywords=(),
            geography=(),
            time_start="2019-04-02",
            time_end="2026-11-13",
            data_types=(),
            notes="",
        )
        DepositMetadataWriter(client).fill_metadata("/datalumos/9", metadata)
        client.add_organization.assert_called_once()
        client.add_person.assert_called_once()
        client.add_date_range.assert_called_once()


if __name__ == "__main__":
    unittest.main()
