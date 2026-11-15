"""Unit tests for SectionChunker."""

import pytest

from backend.data.chunker import SectionChunker


def test_chunk_single_short_text() -> None:
    """Verify text shorter than target size produces a single chunk with index 0."""
    chunker = SectionChunker(chunk_size=1000, overlap=100)
    text = "Short section text explaining Apple's product line and corporate structure."

    chunks = chunker.chunk_section(
        section_text=text,
        company_ticker="AAPL",
        company_cik="0000320193",
        company_name="Apple Inc.",
        accession_number="0000320193-23-000106",
        filing_type="10-K",
        filing_date="2023-11-03",
        report_date="2023-09-30",
        section_identifier="ITEM_1",
        section_title="Item 1. Business",
        source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
        base_offset=500,
    )

    assert len(chunks) == 1
    c = chunks[0]
    assert c.chunk_index == 0
    assert c.company_ticker == "AAPL"
    assert c.company_cik == "0000320193"
    assert c.company_name == "Apple Inc."
    assert c.accession_number == "0000320193-23-000106"
    assert c.filing_type == "10-K"
    assert c.section_identifier == "ITEM_1"
    assert c.section_title == "Item 1. Business"
    assert c.chunk_text == text
    assert c.char_count == len(text)
    assert c.start_offset == 500
    assert c.end_offset == 500 + len(text)


def test_chunk_multiple_long_text() -> None:
    """Verify text significantly longer than chunk size splits into multiple sequential chunks."""
    chunker = SectionChunker(chunk_size=300, overlap=50)

    # 4 distinct paragraphs of ~150 chars each -> ~600 chars total
    p1 = "Paragraph 1: The Company designs and manufactures hardware devices including smartphones and laptops."
    p2 = "Paragraph 2: Services offerings include digital content, streaming services, and advertising platforms."
    p3 = "Paragraph 3: International sales represent a majority of total net sales across all key operating segments."
    p4 = "Paragraph 4: Research and development expenditures continue to support long-term product innovation."
    long_text = f"{p1}\n\n{p2}\n\n{p3}\n\n{p4}"

    chunks = chunker.chunk_section(
        section_text=long_text,
        company_ticker="AAPL",
        company_cik="0000320193",
        company_name="Apple Inc.",
        accession_number="0000320193-23-000106",
        filing_type="10-K",
        filing_date="2023-11-03",
        report_date="2023-09-30",
        section_identifier="ITEM_1",
        section_title="Item 1. Business",
        source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
    )

    assert len(chunks) > 1
    for i, c in enumerate(chunks):
        assert c.chunk_index == i
        assert len(c.chunk_text) > 0


def test_chunk_boundary_preservation() -> None:
    """Verify chunking splits cleanly at paragraph or sentence breaks rather than mid-word."""
    chunker = SectionChunker(chunk_size=200, overlap=40)

    sentence_1 = "First sentence about revenue and operating margin."
    sentence_2 = "Second sentence discussing capital expenditures and liquidity."
    sentence_3 = "Third sentence evaluating risks regarding macroeconomic volatility."
    text = f"{sentence_1}\n\n{sentence_2}\n\n{sentence_3}"

    chunks = chunker.chunk_section(
        section_text=text,
        company_ticker="MSFT",
        company_cik="0000789019",
        company_name="Microsoft Corp",
        accession_number="0000789019-23-000085",
        filing_type="10-K",
        filing_date="2023-08-01",
        report_date="2023-06-30",
        section_identifier="ITEM_7",
        section_title="Item 7. MD&A",
        source_url="https://www.sec.gov/Archives/edgar/data/789019/000078901923000085/msft-20230630.htm",
    )

    # Verify first chunk doesn't cut mid-word
    first_chunk = chunks[0].chunk_text
    assert first_chunk.endswith((".", "\n"))


def test_chunk_overlap_correctness() -> None:
    """Verify consecutive chunks share an overlap window."""
    chunker = SectionChunker(chunk_size=250, overlap=60)

    p1 = "Alpha sentence detailing corporate assets and short-term debt."
    p2 = "Beta sentence discussing cash flow generation and working capital changes."
    p3 = "Gamma sentence highlighting strategic acquisitions and goodwill impairment."
    p4 = "Delta sentence reviewing dividend declarations and treasury stock purchases."
    text = f"{p1}\n\n{p2}\n\n{p3}\n\n{p4}"

    chunks = chunker.chunk_section(
        section_text=text,
        company_ticker="NVDA",
        company_cik="0001045810",
        company_name="NVIDIA CORP",
        accession_number="0001045810-24-000029",
        filing_type="10-K",
        filing_date="2024-02-21",
        report_date="2024-01-28",
        section_identifier="ITEM_7A",
        section_title="Item 7A. Market Risk",
        source_url="https://www.sec.gov/Archives/edgar/data/1045810/000104581024000029/nvda-20240128.htm",
    )

    assert len(chunks) >= 2
    # Verify that text at the end of chunk 0 appears near the beginning of chunk 1
    # Check trailing 30 characters of chunk 0
    words_chunk0 = chunks[0].chunk_text.split()
    trailing_word = words_chunk0[-1]
    assert trailing_word in chunks[1].chunk_text


def test_chunker_deterministic() -> None:
    """Verify chunking the same text twice produces identical chunks."""
    chunker = SectionChunker(chunk_size=300, overlap=50)
    text = "Detailed financial commentary. " * 30

    params = {
        "section_text": text,
        "company_ticker": "AAPL",
        "company_cik": "0000320193",
        "company_name": "Apple Inc.",
        "accession_number": "0000320193-23-000106",
        "filing_type": "10-K",
        "filing_date": "2023-11-03",
        "report_date": "2023-09-30",
        "section_identifier": "ITEM_1A",
        "section_title": "Item 1A. Risk Factors",
        "source_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
    }

    run1 = chunker.chunk_section(**params)
    run2 = chunker.chunk_section(**params)

    assert len(run1) == len(run2)
    for c1, c2 in zip(run1, run2, strict=True):
        assert c1.chunk_index == c2.chunk_index
        assert c1.chunk_text == c2.chunk_text
        assert c1.start_offset == c2.start_offset
        assert c1.end_offset == c2.end_offset
        assert c1.char_count == c2.char_count


def test_chunker_invalid_overlap_raises() -> None:
    """Verify ValueError is raised if overlap >= chunk_size."""
    with pytest.raises(
        ValueError, match="Chunk overlap .* must be smaller than target chunk size"
    ):
        SectionChunker(chunk_size=500, overlap=500)

    with pytest.raises(
        ValueError, match="Chunk overlap .* must be smaller than target chunk size"
    ):
        SectionChunker(chunk_size=500, overlap=600)


def test_chunker_empty_text() -> None:
    """Verify empty or whitespace text returns an empty list."""
    chunker = SectionChunker()
    params = {
        "company_ticker": "AAPL",
        "company_cik": "0000320193",
        "company_name": "Apple Inc.",
        "accession_number": "0000320193-23-000106",
        "filing_type": "10-K",
        "filing_date": "2023-11-03",
        "report_date": "2023-09-30",
        "section_identifier": "ITEM_1",
        "section_title": "Item 1. Business",
        "source_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
    }
    assert chunker.chunk_section(section_text="", **params) == []
    assert chunker.chunk_section(section_text="   \n\n  ", **params) == []
