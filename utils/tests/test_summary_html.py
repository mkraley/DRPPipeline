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

    def test_prepare_unescapes_embedded_anchor_and_image(self) -> None:
        """Escaped tags inside a paragraph are pasted as HTML."""
        raw = (
            "<p>Kelso S &lt;a target=&quot;_blank&quot; "
            "href=&quot;https://orcid.org/0009-0002-8468-6945&quot;&gt;"
            "&lt;img src=&quot;/DataStore/Resources/Images/Icons/ORCID.png&quot; "
            "alt=&quot;ORCID&quot;&gt;&lt;/a&gt; wrote it.</p>"
        )
        result = prepare_summary_for_datalumos_upload(raw)
        assert "&lt;" not in result
        assert "<img" in result
        assert 'href="https://orcid.org/0009-0002-8468-6945"' in result
        assert "Kelso S" in result

    def test_anchor_keeps_its_text_and_drops_image(self) -> None:
        """A link's visible text stays, and an image beside it is omitted."""
        raw = '<p>See <a href="https://example.com">the paper</a> <img src="x.png" alt="chart">.</p>'
        result = normalize_summary_html_for_datalumos(raw)
        assert "<img" not in result
        assert "chart" not in result
        assert 'href="https://example.com"' in result
        assert "the paper" in result

    def test_prepare_summary_for_datalumos_upload_decodes_entities(self) -> None:
        """Entity-encoded paragraphs are unescaped and joined with line breaks."""
        raw = "&lt;p&gt;First.&lt;/p&gt;&lt;p&gt;Second.&lt;/p&gt;"
        result = prepare_summary_for_datalumos_upload(raw)
        assert result == "<p>First.<br><br>Second.</p>"

    def test_prepare_turns_strong_into_b_and_keeps_breaks(self) -> None:
        """DataLumos keeps b and br, and strips strong and adjacent p tags."""
        raw = "<h2>Overview</h2><p><strong>Citation:</strong> Kelso</p><p>Next.</p>"
        result = prepare_summary_for_datalumos_upload(raw)
        assert result == "<p><b>Overview</b><br><br><b>Citation:</b> Kelso<br><br>Next.</p>"
        assert "<strong>" not in result
