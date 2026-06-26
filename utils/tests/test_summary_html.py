"""Tests for summary HTML normalization utilities."""

from __future__ import annotations

from utils.summary_html import (
    normalize_summary_html_for_datalumos,
    prepare_summary_for_datalumos_upload,
    structure_summary_for_wysihtml5,
    summary_html_to_plain_text,
)


class TestSummaryHtml:
    """Tests for DataLumos summary HTML helpers."""

    def test_wraps_plain_text_in_paragraph(self) -> None:
        """Plain summaries become a single paragraph."""
        result = normalize_summary_html_for_datalumos("Field measurements from 2014.")
        assert result == "<p>Field measurements from 2014.</p>"

    def test_preserves_links_and_paragraphs(self) -> None:
        """Figshare-style HTML keeps links and paragraph structure."""
        raw = (
            '<p dir="ltr">See <a href="https://doi.org/10.1000/example">related work</a>.</p>'
            '<p dir="ltr"><strong>Methods</strong> are described below.</p>'
        )
        result = normalize_summary_html_for_datalumos(raw)
        assert 'href="https://doi.org/10.1000/example"' in result
        assert "<strong>Methods</strong>" in result
        assert "dir=" not in result
        assert result.count("<p>") == 2

    def test_unescapes_entity_encoded_html(self) -> None:
        """Double-encoded summaries are decoded before cleanup."""
        raw = "&lt;p&gt;Encoded summary&lt;/p&gt;"
        result = normalize_summary_html_for_datalumos(raw)
        assert result == "<p>Encoded summary</p>"

    def test_strips_disallowed_tags(self) -> None:
        """Unsupported tags are removed while keeping inner text."""
        raw = '<p><span style="color:red">Important</span> note</p>'
        result = normalize_summary_html_for_datalumos(raw)
        assert "<span" not in result
        assert "Important" in result

    def test_summary_html_to_plain_text(self) -> None:
        """Plain text extraction keeps readable paragraph breaks."""
        raw = "<p>Line one.</p><p>Line <strong>two</strong>.</p>"
        plain = summary_html_to_plain_text(raw)
        assert "Line one." in plain
        assert "Line two." in plain
        assert "<p>" not in plain

    def test_structure_summary_for_wysihtml5_joins_paragraphs(self) -> None:
        """Multiple paragraphs become one block with explicit line breaks."""
        raw = "<p>First paragraph.</p><p>Second with <a href=\"https://x.com\">link</a>.</p>"
        result = structure_summary_for_wysihtml5(raw)
        assert result == (
            "<p>First paragraph.<br><br>Second with "
            '<a href="https://x.com">link</a>.</p>'
        )

    def test_prepare_summary_for_datalumos_upload_decodes_entities(self) -> None:
        """Entity-encoded DB exports are decoded and structured for upload."""
        raw = "&lt;p&gt;First.&lt;/p&gt;&lt;p&gt;Second.&lt;/p&gt;"
        result = prepare_summary_for_datalumos_upload(raw)
        assert "<br><br>" in result
        assert "&lt;" not in result
        assert "First." in result
        assert "Second." in result
