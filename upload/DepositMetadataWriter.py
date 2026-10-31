"""
Write prepared metadata through :class:`DataLumosDepositClient`.

Each field is one request. Attributes are loaded once and not refreshed between posts.
"""

from __future__ import annotations

from upload.DataLumosDepositClient import DataLumosDepositClient
from upload.DepositAttribute import (
    DepositAttribute,
    checklist_wire_value,
    list_slot_id,
    scalar_data_id,
    tilde_join,
)
from upload.DepositMetadata import DepositMetadata
from upload.deposit_field_match import match_fields
from utils.Logger import Logger


class DepositMetadataWriter:
    """Post one project's metadata without reloading the workspace between fields."""

    def __init__(self, client: DataLumosDepositClient) -> None:
        """Args: client: Authenticated deposit client."""
        self._client = client
        self._attributes: list[DepositAttribute] = []

    def fill_metadata(self, path: str, metadata: DepositMetadata) -> None:
        """
        Write metadata fields that have values.

        Raises:
            RuntimeError: When a provided field has no matching attribute, or a post fails.
        """
        self._attributes = self._client.get_attributes(path)
        matched = match_fields(self._attributes)
        self._write_agencies(path, matched, metadata.agencies)
        self._write_investigators(path, matched, metadata.investigators)
        self._write_text(path, matched, "summary", metadata.summary)
        self._write_text(path, matched, "original_url", metadata.original_url)
        self._write_keywords(path, matched, metadata.keywords)
        self._write_terms(path, matched, "geography", metadata.geography)
        self._write_time_period(path, matched, metadata)
        self._write_data_types(path, matched, metadata.data_types)
        self._write_text(path, matched, "notes", metadata.notes)

    def _write_text(
        self,
        path: str,
        matched: dict[str, DepositAttribute],
        field: str,
        value: str,
    ) -> None:
        """Post one scalar field when ``value`` is non-empty."""
        if not value:
            return
        attr = self._require(matched, field)
        self._client.post_property(path, scalar_data_id(attr), value, attr.label)

    def _write_terms(
        self,
        path: str,
        matched: dict[str, DepositAttribute],
        field: str,
        values: tuple[str, ...],
    ) -> None:
        """Post each list entry as its own add-value slot."""
        if not values:
            return
        attr = self._require(matched, field)
        for index, term in enumerate(values, start=1):
            self._client.post_property(path, list_slot_id(attr, index), term, attr.label)

    def _write_agencies(
        self,
        path: str,
        matched: dict[str, DepositAttribute],
        agencies: tuple[str, ...],
    ) -> None:
        """Post each agency through the organization endpoint."""
        if not agencies:
            return
        attr = self._require(matched, "agency")
        for org_name in agencies:
            self._client.add_organization(path, attr.key, org_name)

    def _write_investigators(
        self,
        path: str,
        matched: dict[str, DepositAttribute],
        people: tuple[tuple[str, str, str], ...],
    ) -> None:
        """Post each investigator through the person endpoint."""
        if not people:
            return
        attr = self._require(matched, "investigators")
        for first_name, last_name, affiliation in people:
            self._client.add_person(path, attr.key, first_name, last_name, affiliation)

    def _write_keywords(
        self,
        path: str,
        matched: dict[str, DepositAttribute],
        keywords: tuple[str, ...],
    ) -> None:
        """Resolve subject terms, then post them as one ``~~``-joined value."""
        if not keywords:
            return
        attr = self._require(matched, "keywords")
        resolved = [self._resolve_subject_term(term) for term in keywords]
        self._client.post_property(
            path,
            scalar_data_id(attr),
            tilde_join(resolved),
            attr.label,
        )

    def _write_time_period(
        self,
        path: str,
        matched: dict[str, DepositAttribute],
        metadata: DepositMetadata,
    ) -> None:
        """Post the time period when a start date is present."""
        if not metadata.time_start and not metadata.time_end:
            return
        if not metadata.time_start:
            raise RuntimeError("Time period requires a start date")
        attr = self._require(matched, "time_period")
        self._client.add_date_range(
            path,
            attr.ui_control or "timePeriod",
            metadata.time_start,
            metadata.time_end,
        )

    def _write_data_types(
        self,
        path: str,
        matched: dict[str, DepositAttribute],
        data_types: tuple[str, ...],
    ) -> None:
        """Post kind-of-data labels as one checklist value."""
        if not data_types:
            return
        attr = self._require(matched, "data_types")
        wire = [checklist_wire_value(label) for label in data_types]
        self._client.post_property(path, scalar_data_id(attr), tilde_join(wire), attr.label)

    def _resolve_subject_term(self, term: str) -> str:
        """
        Return the thesaurus spelling when the term is listed, otherwise the text as entered.

        Subject Terms select2 allows tags that are not in the suggestion list.
        """
        wanted = term.casefold()
        for suggestion in self._client.suggest_subject_terms(term):
            if suggestion.casefold() == wanted:
                return suggestion
        Logger.warning(
            "Subject term %r is not in the DataLumos thesaurus; posting it as entered",
            term,
        )
        return term

    def _require(
        self,
        matched: dict[str, DepositAttribute],
        field: str,
    ) -> DepositAttribute:
        """Return the attribute for ``field`` or raise with the labels we did see."""
        attr = matched.get(field)
        if attr is not None:
            return attr
        labels = ", ".join(sorted({item.label for item in self._attributes if item.label}))
        raise RuntimeError(f"No deposit attribute for {field}. Labels: {labels}")
