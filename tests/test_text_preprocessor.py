"""Unit tests for TextPreprocessor."""

from backend.retrieval.text_preprocessor import TextPreprocessor


def test_clean_text_whitespace_normalization() -> None:
    """Verify excessive spaces and line breaks are collapsed while preserving paragraphs."""
    raw = "  This   is    Item   1A.   \n\n\n\nRisk   Factors.   \t  Global supply  chain.  "
    cleaned = TextPreprocessor.clean_text(raw)
    assert cleaned == "This is Item 1A.\n\nRisk Factors. Global supply chain."


def test_clean_text_preserves_financial_numbers_and_symbols() -> None:
    """Verify monetary symbols, percentages, decimals, and negative signs remain intact."""
    raw = (
        "Revenue grew by 8.5% to $383,285,000,000 in FY 2023. "
        "Operating margin was 29.8%. CapEx was -$10.96B (or -10,959M USD)."
    )
    cleaned = TextPreprocessor.clean_text(raw)
    assert "$383,285,000,000" in cleaned
    assert "8.5%" in cleaned
    assert "29.8%" in cleaned
    assert "-$10.96B" in cleaned
    assert "-10,959M USD" in cleaned


def test_clean_text_preserves_table_pipe_delimiters() -> None:
    """Verify structured pipe-delimited table rows are preserved."""
    raw = (
        "Fiscal Year | 2023 | 2022\n"
        "Revenue     | $383,285 | $394,328\n"
        "Net Income  | $96,995  | $99,803\n"
    )
    cleaned = TextPreprocessor.clean_text(raw)
    assert "Fiscal Year | 2023 | 2022" in cleaned
    assert "Revenue | $383,285 | $394,328" in cleaned
    assert "Net Income | $96,995 | $99,803" in cleaned


def test_prepare_chunk_text_with_context() -> None:
    """Verify contextual metadata prefix is prepended to cleaned chunk content."""
    chunk = "Supply chain disruptions may adversely impact operations."
    prepared = TextPreprocessor.prepare_chunk_text(
        chunk_text=chunk,
        ticker="aapl",
        filing_type="10-k",
        section_title="Item 1A. Risk Factors",
        include_context=True,
    )
    assert prepared.startswith(
        "Company: AAPL | Filing: 10-K | Section: Item 1A. Risk Factors | Content: "
    )
    assert "Supply chain disruptions" in prepared


def test_prepare_chunk_text_without_context() -> None:
    """Verify text is returned cleaned without context prefix when include_context is False."""
    chunk = "  Supply chain disruptions.  "
    prepared = TextPreprocessor.prepare_chunk_text(
        chunk_text=chunk,
        ticker="AAPL",
        filing_type="10-K",
        include_context=False,
    )
    assert prepared == "Supply chain disruptions."


def test_compute_hashes() -> None:
    """Verify hash functions produce deterministic SHA-256 digests."""
    text1 = "Some financial text"
    text2 = "Some financial text"
    text3 = "Different text"

    h1 = TextPreprocessor.compute_text_hash(text1)
    h2 = TextPreprocessor.compute_text_hash(text2)
    h3 = TextPreprocessor.compute_text_hash(text3)

    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64

    input_hash = TextPreprocessor.compute_input_hash(
        chunk_text=text1,
        ticker="AAPL",
        filing_type="10-K",
        section_title="Risk Factors",
    )
    assert len(input_hash) == 64
    assert input_hash != h1


def test_clean_text_empty_input() -> None:
    """Verify empty or whitespace strings return empty string."""
    assert TextPreprocessor.clean_text("") == ""
    assert TextPreprocessor.clean_text("   \n\t  ") == ""
    assert TextPreprocessor.prepare_chunk_text("") == ""
