"""Tests for FERC catalog keywords."""

from __future__ import annotations

import unittest

from collectors.FercKeywords import FREE_TEXT_TERMS, keywords_for_ferc, rule_terms
from utils.IcpsrSubjectThesaurus import IcpsrSubjectThesaurus

_TITLES = (
    "Form 552 Master Table",
    "Form 552 Page 3",
    "Oil Assessment Table",
    "Oil Debit/Credit Calculations",
    "Electric Assessment Table",
    "Electric Debit/Credit Calculations",
    "Gas Assessments",
    "Gas Debit/Credit Calculations",
    "Gen Assets",
    "MBR Authorizations",
    "MBR Category Status",
    "MBR Mitigations",
    "MBR Self Limitations",
    "MBR Operating Reserves",
    "Entities to Entities",
    "Entities to Vertical Assets",
    "Entities to Gen Assets",
    "Entities to PPAs",
    "Indicative Market Share Screens",
    "Indicative Pivotal Supplier Screens",
    "Information Collections - Approved",
    "Administrative Hydropower Actual",
    "Administrative Hydropower Estimate",
    "Administrative Hydropower Fixed Charges (Actual)",
    "Administrative Hydropower Fixed Charges (Estimate)",
    "Other Federal Agencies Cost Assessment",
    "FERC Company Identifier Listing",
    "NEPA Schedule for Pending Infrastructure Projects",
    "Respondent Information",
    "Shipper and Contract Information",
    "Active Exemptions",
    "Active Licenses",
    "Projects by Relicensing Due Date",
    "Licensed Marine and Hydrokinetic Projects",
    "Index of Customer Quarterly Filings",
    "FERC Form 556",
    "Direct Ownership",
    "Upstream (Indirect) Ownership",
    "Affiliated Small Power Production QFs",
    "Topping-Cycle Thermal Host",
    "Bottoming-Cycle Thermal Host",
    "Notices of Intent to Construct Qualifying Conduit Hydropower Facilities",
    "Form 1 Comparative Balance Sheet",
    "Form 1 Statement of Income",
    "Form 1 Electric Plant in Service",
    "Form 6 Annual Cost of Service Based Analysis Schedule",
    "Form 1 Electric Operation and Maintenance Expenses",
)


class TestFercKeywords(unittest.TestCase):
    """Keywords name the form or program and a shared subject."""

    def test_form_552_keeps_the_form_number_and_splits_the_price_index_page(self) -> None:
        """The master table and page 3 share Form 552; page 3 adds price indexes."""
        master = keywords_for_ferc("Form 552 Master Table")
        page = keywords_for_ferc("Form 552 Page 3")
        self.assertIn("Form 552", master)
        self.assertIn("natural gas", master)
        self.assertNotIn("form master table", master)
        self.assertIn("price indexes", page)
        self.assertNotIn("price indexes", master)

    def test_related_tables_share_a_subject(self) -> None:
        """Market-based rate tables and hydropower tables retrieve together."""
        authorizations = keywords_for_ferc("MBR Authorizations")
        entities = keywords_for_ferc("Entities to Entities")
        licenses = keywords_for_ferc("Active Licenses")
        marine = keywords_for_ferc("Licensed Marine and Hydrokinetic Projects")
        self.assertIn("market-based rates", authorizations)
        self.assertIn("electric utilities", authorizations)
        self.assertNotIn("entities entities", entities)
        self.assertIn("ownership", entities)
        self.assertIn("hydropower", licenses)
        self.assertIn("licenses", licenses)
        self.assertIn("hydrokinetic", marine)
        self.assertIn("hydropower", marine)

    def test_every_catalog_title_matches(self) -> None:
        """Each sourced dataset title receives keywords."""
        for title in _TITLES:
            self.assertTrue(keywords_for_ferc(title), title)

    def test_terms_are_thesaurus_labels_or_known_search_names(self) -> None:
        """A keyword is an ICPSR preferred term or a name we deliberately keep."""
        thesaurus = IcpsrSubjectThesaurus.load()
        for term in rule_terms():
            self.assertTrue(
                thesaurus.contains(term) or term in FREE_TEXT_TERMS,
                term,
            )


if __name__ == "__main__":
    unittest.main()
