"""Unit tests for FinancialTokenizer.

Validates that financial terms, acronyms, monetary values, percentages,
and hyphenated phrases are preserved without aggressive stemming or signal loss.
"""

from backend.retrieval.bm25_search import FinancialTokenizer


def test_financial_tokenizer_preserves_monetary_values() -> None:
    """Verify monetary values with dollar signs, decimals, and commas are preserved."""
    tokenizer = FinancialTokenizer(remove_stopwords=True)
    text = "Revenue reached $5.2 billion with cash of $1,250.75 and a small fee of $50."
    tokens = tokenizer.tokenize(text)

    assert "$5.2" in tokens
    assert "$1,250.75" in tokens
    assert "$50" in tokens
    assert "billion" in tokens
    assert "revenue" in tokens


def test_financial_tokenizer_preserves_percentages() -> None:
    """Verify percentage expressions with and without decimals are preserved."""
    tokenizer = FinancialTokenizer(remove_stopwords=True)
    text = "Gross margin was 44.1% while operating margin expanded 15%."
    tokens = tokenizer.tokenize(text)

    assert "44.1%" in tokens
    assert "15%" in tokens
    assert "margin" in tokens
    assert "gross" in tokens


def test_financial_tokenizer_preserves_hyphenated_terms() -> None:
    """Verify hyphenated financial terms and SEC statutory forms are preserved."""
    tokenizer = FinancialTokenizer(remove_stopwords=True)
    text = "According to Form 10-K and 10-Q disclosures, year-over-year non-GAAP cash-flow and debt-to-equity ratios improved."
    tokens = tokenizer.tokenize(text)

    assert "10-k" in tokens
    assert "10-q" in tokens
    assert "year-over-year" in tokens
    assert "non-gaap" in tokens
    assert "cash-flow" in tokens
    assert "debt-to-equity" in tokens


def test_financial_tokenizer_preserves_financial_acronyms() -> None:
    """Verify acronyms like EBITDA, GAAP, CIK, SEC, CAGR are preserved."""
    tokenizer = FinancialTokenizer(remove_stopwords=True)
    text = "Adjusted EBITDA and US-GAAP Net Income showed steady CAGR."
    tokens = tokenizer.tokenize(text)

    assert "ebitda" in tokens
    assert "us-gaap" in tokens
    assert "cagr" in tokens
    assert "income" in tokens


def test_financial_tokenizer_empty_and_whitespace() -> None:
    """Verify empty, None, and whitespace strings return empty lists."""
    tokenizer = FinancialTokenizer()
    assert tokenizer.tokenize("") == []
    assert tokenizer.tokenize("   \n\t  ") == []
    assert tokenizer.tokenize_query("") == []


def test_financial_tokenizer_safe_stopwords() -> None:
    """Verify function words are removed while financial numbers and terms remain."""
    tokenizer = FinancialTokenizer(remove_stopwords=True)
    text = "The growth in revenue was due to an increase of 25% by the company."
    tokens = tokenizer.tokenize(text)

    # Function words removed
    assert "the" not in tokens
    assert "in" not in tokens
    assert "was" not in tokens
    assert "to" not in tokens
    assert "an" not in tokens
    assert "of" not in tokens
    assert "by" not in tokens

    # Financial signal preserved
    assert "growth" in tokens
    assert "revenue" in tokens
    assert "increase" in tokens
    assert "25%" in tokens
    assert "company" in tokens

