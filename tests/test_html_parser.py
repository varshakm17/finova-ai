"""Tests for HTMLDocumentParser, inline XBRL unwrapping, and table formatting."""

from backend.data.html_parser import HTMLDocumentParser
from tests.fixtures.sec_html_fixtures import SAMPLE_10K_HTML, SAMPLE_INLINE_XBRL_HTML


def test_html_parser_normal_extraction() -> None:
    """Verify normal HTML parsing extracts headings, paragraphs, and tables."""
    parser = HTMLDocumentParser()
    text = parser.parse_html(SAMPLE_10K_HTML)

    assert "UNITED STATES SECURITIES AND EXCHANGE COMMISSION" in text
    assert "FORM 10-K ANNUAL REPORT" in text
    assert "ITEM 1. BUSINESS" in text
    assert "ITEM 1A. RISK FACTORS" in text
    assert "ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS" in text
    assert "ITEM 7A. QUANTITATIVE AND QUALITATIVE DISCLOSURES" in text

    # Verify script content was completely removed
    assert "Analytics script that must be stripped" not in text

    # Verify hidden element was removed
    assert "Hidden non-content tracking snippet" not in text

    # Verify table formatting (pipe separated)
    assert "Semiconductors | Single-source supply constraints" in text
    assert "Display Modules | High manufacturing complexity" in text


def test_html_parser_inline_xbrl() -> None:
    """Verify inline XBRL tags (<ix:nonFraction>, <ix:nonNumeric>) are unwrapped preserving inner text."""
    parser = HTMLDocumentParser()
    text = parser.parse_html(SAMPLE_INLINE_XBRL_HTML)

    assert "Our total revenue was 383,285 million" in text
    assert "Services segment" in text
    assert "<ix:" not in text


def test_html_parser_malformed_html() -> None:
    """Verify malformed and incomplete HTML is parsed gracefully without crashing."""
    parser = HTMLDocumentParser()
    malformed = "<html><body><h3>Unclosed Heading<p>Paragraph without closing body"
    text = parser.parse_html(malformed)

    assert "Unclosed Heading" in text
    assert "Paragraph without closing body" in text


def test_html_parser_empty_content() -> None:
    """Verify empty content returns empty string."""
    parser = HTMLDocumentParser()
    assert parser.parse_html("") == ""
    assert parser.parse_html(None) == ""
