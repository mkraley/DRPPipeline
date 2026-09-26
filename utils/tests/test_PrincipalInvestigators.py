"""Tests for principal investigator serialization and parsing."""

from utils.PrincipalInvestigators import (
    coalesce_corporate_affiliations,
    deserialize_investigators,
    investigators_from_irma_contacts,
    parse_display_person,
    serialize_investigators,
)


class TestPrincipalInvestigators:
    def test_serialize_round_trip(self) -> None:
        people = [
            {
                "first_name": "Brian",
                "last_name": "Witcher",
                "affiliation": "National Park Service",
            }
        ]
        encoded = serialize_investigators(people)
        assert deserialize_investigators(encoded) == people

    def test_parse_display_person_with_affiliation(self) -> None:
        assert parse_display_person("Brian Witcher (National Park Service)") == {
            "first_name": "Brian",
            "last_name": "Witcher",
            "affiliation": "National Park Service",
        }

    def test_investigators_from_irma_contacts(self) -> None:
        raw = [
            {
                "firstName": "Evan",
                "primaryName": "Raskin",
                "affiliation": "National Park Service",
            }
        ]
        assert investigators_from_irma_contacts(raw) == [
            {
                "first_name": "Evan",
                "last_name": "Raskin",
                "affiliation": "National Park Service",
            }
        ]

    def test_corporate_lead_becomes_affiliation(self) -> None:
        """IRMA isCorporate lead is affiliation for the following person."""
        org = "National Park Service, Arctic Network Inventory & Monitoring Program"
        raw = [
            {
                "primaryName": org,
                "firstName": None,
                "affiliation": None,
                "isCorporate": True,
            },
            {
                "primaryName": "Jorgenson",
                "firstName": "Torre",
                "affiliation": None,
            },
        ]
        assert investigators_from_irma_contacts(raw) == [
            {
                "first_name": "Torre",
                "last_name": "Jorgenson",
                "affiliation": org,
            }
        ]

    def test_coalesce_stored_corporate_last_name(self) -> None:
        """Org saved as last_name merges into the next person's affiliation."""
        org = "National Park Service, Arctic Network Inventory & Monitoring Program"
        people = [
            {"first_name": "", "last_name": org, "affiliation": ""},
            {"first_name": "Torre", "last_name": "Jorgenson", "affiliation": ""},
        ]
        assert coalesce_corporate_affiliations(people) == [
            {
                "first_name": "Torre",
                "last_name": "Jorgenson",
                "affiliation": org,
            }
        ]

    def test_deserialize_merges_corporate_then_person(self) -> None:
        """Legacy Lead text 'Org; First Last' becomes one investigator."""
        org = "National Park Service, Arctic Network Inventory & Monitoring Program"
        people = deserialize_investigators(f"{org}; Torre Jorgenson")
        assert people == [
            {
                "first_name": "Torre",
                "last_name": "Jorgenson",
                "affiliation": org,
            }
        ]

    def test_deserialize_legacy_semicolon_list(self) -> None:
        raw = "Brian Witcher (NPS); Evan Raskin (NPS)"
        people = deserialize_investigators(raw)
        assert len(people) == 2
        assert people[0]["last_name"] == "Witcher"
        assert people[1]["first_name"] == "Evan"
