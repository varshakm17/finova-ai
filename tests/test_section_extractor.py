"""Unit tests for filing SectionExtractor."""

from backend.data.html_parser import HTMLDocumentParser
from backend.data.section_extractor import SectionExtractor
from tests.fixtures.sec_html_fixtures import SAMPLE_10K_HTML, SAMPLE_10Q_HTML


def test_extract_sections_10k() -> None:
    """Verify prioritized sections (Item 1, 1A, 7, 7A) are extracted from 10-K text."""
    parser = HTMLDocumentParser()
    text = parser.parse_html(SAMPLE_10K_HTML)

    extractor = SectionExtractor(min_section_chars=100)
    sections = extractor.extract_sections(text, form_type="10-K")

    sec_map = {s.section_identifier: s for s in sections}

    # Verify all 4 canonical items are present
    assert "ITEM_1" in sec_map
    assert "ITEM_1A" in sec_map
    assert "ITEM_7" in sec_map
    assert "ITEM_7A" in sec_map

    # Item 1: Business
    item_1 = sec_map["ITEM_1"]
    assert item_1.status == "extracted"
    assert item_1.char_count > 100
    assert "Apple Inc. designs, manufactures, and markets" in item_1.text
    assert item_1.start_char >= 0
    assert item_1.end_char > item_1.start_char

    # Item 1A: Risk Factors
    item_1a = sec_map["ITEM_1A"]
    assert item_1a.status == "extracted"
    assert "The Company's business, reputation, results of operations" in item_1a.text
    assert "Semiconductors | Single-source supply constraints" in item_1a.text

    # Item 7: MD&A
    item_7 = sec_map["ITEM_7"]
    assert item_7.status == "extracted"
    assert "Total net sales decreased 3% or $11.0 billion" in item_7.text
    assert "Operating income was $114.3 billion in 2023." in item_7.text

    # Item 7A: Market Risk
    item_7a = sec_map["ITEM_7A"]
    assert item_7a.status == "extracted"
    assert "investment portfolio is subject to interest rate risk" in item_7a.text


def test_extract_sections_10q() -> None:
    """Verify 10-Q item mappings (Part I Item 2 -> ITEM_7, Part I Item 3 -> ITEM_7A, Part II Item 1A -> ITEM_1A)."""
    parser = HTMLDocumentParser()
    text = parser.parse_html(SAMPLE_10Q_HTML)

    extractor = SectionExtractor(min_section_chars=100)
    sections = extractor.extract_sections(text, form_type="10-Q")

    sec_map = {s.section_identifier: s for s in sections}

    assert "ITEM_7" in sec_map
    assert "ITEM_7A" in sec_map
    assert "ITEM_1A" in sec_map

    # MD&A from Part I Item 2
    item_7 = sec_map["ITEM_7"]
    assert item_7.status == "extracted"
    assert (
        "Net sales were $81.8 billion for the three months ended July 1, 2023"
        in item_7.text
    )

    # Market Risk from Part I Item 3
    item_7a = sec_map["ITEM_7A"]
    assert item_7a.status == "extracted"
    assert "no material changes to the market risk disclosures" in item_7a.text

    # Risk Factors from Part II Item 1A
    item_1a = sec_map["ITEM_1A"]
    assert item_1a.status == "extracted"
    assert (
        "no material changes from the risk factors previously disclosed" in item_1a.text
    )


def test_toc_rejection() -> None:
    """Verify Table of Contents listings are skipped and only substantive content is captured."""
    # Synthetic text with compact TOC followed by substantive section
    raw_text = """
TABLE OF CONTENTS
Item 1. Business ................ Page 4
Item 1A. Risk Factors ........... Page 15
Item 7. MD&A .................... Page 30

PART I

ITEM 1. BUSINESS
This is the substantive business section of the company. It describes products, services,
target demographics, geographic revenue concentration, and manufacturing logistics across
North America, Europe, Greater China, and the Rest of Asia Pacific.

ITEM 1A. RISK FACTORS
This is the substantive risk factors section describing economic and operational headwinds.
"""
    extractor = SectionExtractor(min_section_chars=100)
    sections = extractor.extract_sections(raw_text, form_type="10-K")

    item_1 = next(s for s in sections if s.section_identifier == "ITEM_1")
    assert item_1.status == "extracted"
    assert "substantive business section of the company" in item_1.text
    # Ensure TOC line was not captured as the section content
    assert "Page 4" not in item_1.text


def test_missing_sections_handled_gracefully() -> None:
    """Verify missing sections return status 'not_found' without crashing."""
    text_without_mda = """
ITEM 1. BUSINESS
The company manufactures widgets for enterprise and commercial clients. We operate across
three principal reporting segments with diversified distribution channels worldwide.

ITEM 1A. RISK FACTORS
Operating in foreign jurisdictions presents regulatory, compliance, and currency volatility risks.
"""
    extractor = SectionExtractor(min_section_chars=50)
    sections = extractor.extract_sections(text_without_mda, form_type="10-K")

    sec_map = {s.section_identifier: s for s in sections}
    assert sec_map["ITEM_1"].status == "extracted"
    assert sec_map["ITEM_1A"].status == "extracted"
    assert sec_map["ITEM_7"].status == "not_found"
    assert sec_map["ITEM_7"].char_count == 0
    assert sec_map["ITEM_7"].text == ""


def test_empty_or_whitespace_text() -> None:
    """Verify empty or whitespace-only text returns an empty list."""
    extractor = SectionExtractor()
    assert extractor.extract_sections("") == []
    assert extractor.extract_sections("   \n\n  ") == []


def test_uncertain_status_when_only_short_snippets() -> None:
    """Verify status is 'uncertain' when section heading exists but candidate text is below min_section_chars."""
    short_text = """
ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS
See Item 8.
ITEM 8. FINANCIAL STATEMENTS
"""
    extractor = SectionExtractor(min_section_chars=150)
    sections = extractor.extract_sections(short_text, form_type="10-K")

    item_7 = next(s for s in sections if s.section_identifier == "ITEM_7")
    assert item_7.status == "uncertain"
    assert item_7.char_count == 0
