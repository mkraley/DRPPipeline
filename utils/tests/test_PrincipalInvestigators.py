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

    def test_comma_lead_splits_name_and_affiliation(self) -> None:
        """'First Last, org, role' is a person plus affiliation, not one blob."""
        raw = [
            {
                "first_name": "",
                "last_name": "",
                "affiliation": "Pete Biggam, National Park Service, Soils Program Manager",
            }
        ]
        assert investigators_from_irma_contacts(raw) == [
            {
                "first_name": "Pete",
                "last_name": "Biggam",
                "affiliation": "National Park Service, Soils Program Manager",
            }
        ]

    def test_parenthetical_and_bare_names(self) -> None:
        encoded = serialize_investigators(
            [
                {"affiliation": "Jason Kenworthy (NPS GRD)"},
                {"affiliation": "Jennifer Bailard"},
            ]
        )
        people = deserialize_investigators(encoded)
        assert people[0] == {
            "first_name": "Jason",
            "last_name": "Kenworthy",
            "affiliation": "NPS GRD",
        }
        assert people[1] == {
            "first_name": "Jennifer",
            "last_name": "Bailard",
            "affiliation": "",
        }

    def test_organization_is_not_a_principal_investigator(self) -> None:
        """An organization or company lead is omitted, not stored without a name."""
        for text in (
            "Sonoran Desert Network",
            "DJ&A, P.C.",
            "Wildlife Specialists, LLC",
            "Siskiyou BioSurvey LLC",
            "Park Ecologist",
        ):
            assert deserialize_investigators(
                serialize_investigators([{"affiliation": text}])
            ) == []
            assert investigators_from_irma_contacts([{"affiliation": text}]) == []

    def test_named_investigator_is_kept_when_affiliation_has_a_person(self) -> None:
        people = deserialize_investigators(
            '[{"first_name": "", "last_name": "", "affiliation": '
            '"Dean Tucker, National Park Service, Water Resources Division"}]'
        )
        assert people[0]["first_name"] == "Dean"
        assert people[0]["last_name"] == "Tucker"

    def test_mixed_org_and_person_keeps_only_the_person(self) -> None:
        """An organization stored beside a named lead is not itself an investigator."""
        raw = (
            '[{"first_name": "", "last_name": "Sonoran Desert Network", "affiliation": ""},'
            ' {"first_name": "Jennifer", "last_name": "Bailard", "affiliation": ""}]'
        )
        people = deserialize_investigators(raw)
        assert people == [
            {
                "first_name": "Jennifer",
                "last_name": "Bailard",
                "affiliation": "Sonoran Desert Network",
            }
        ]
