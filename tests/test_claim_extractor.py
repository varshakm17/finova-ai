"""Tests for Claim Extraction and Sentence Segmentation (Session 09).

Verifies sentence splitting with abbreviation protection, numeric entity parsing,
period identification, company recognition, and citation mapping.
"""

from backend.verification.claim_extractor import ClaimExtractor
from backend.verification.verification_models import ClaimType


def test_claim_extractor_abbreviations_not_split():
    extractor = ClaimExtractor()
    text = (
        "Apple Inc. reported total net sales of $383.29 billion in FY2023 [E1]. "
        "The U.S. market remained resilient with revenue of $162.6M [E2]. "
        "Operating margin was 29.8% in FY2023 [C1]."
    )
    result = extractor.extract_claims(text)
    claims = result.claims
    assert len(claims) == 3
    assert "Apple Inc. reported" in claims[0].claim_text
    assert "The U.S. market" in claims[1].claim_text
    assert "Operating margin" in claims[2].claim_text


def test_claim_extractor_citations_linked():
    extractor = ClaimExtractor()
    text = "Total revenue grew by 8.0% [E1, C1]. Diluted EPS reached $6.13 [E2]."
    result = extractor.extract_claims(text)
    assert len(result.claims) == 2
    assert "E1" in result.claims[0].citation_ids
    assert "C1" in result.claims[0].citation_ids
    assert "E2" in result.claims[1].citation_ids


def test_claim_extractor_numeric_entities():
    extractor = ClaimExtractor()
    text = "Net income was $96,995 million, representing a 2.8% decrease compared to prior year [E1]."
    result = extractor.extract_claims(text)
    assert len(result.claims) == 1
    claim = result.claims[0]
    assert len(claim.numeric_values) >= 2

    val_97b = [
        v
        for v in claim.numeric_values
        if v.scale_multiplier >= 1e6 or v.numeric_value >= 90000
    ]
    assert len(val_97b) > 0
    assert val_97b[0].normalized_value == 96995000000.0

    val_pct = [v for v in claim.numeric_values if v.is_percentage]
    assert len(val_pct) > 0
    assert val_pct[0].numeric_value == 2.8


def test_claim_extractor_period_detection():
    extractor = ClaimExtractor()
    text = (
        "In FY2023, revenue expanded while maintaining steady operating cash flow [E1]."
    )
    result = extractor.extract_claims(text)
    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.mentioned_period is not None
    assert "2023" in claim.mentioned_period


def test_claim_extractor_company_detection():
    extractor = ClaimExtractor()
    text = (
        "Microsoft reported cloud growth [E1]. AAPL announced share repurchases [E2]."
    )
    result = extractor.extract_claims(text)
    assert len(result.claims) == 2
    assert result.claims[0].mentioned_company in ("Microsoft", "MSFT")
    assert result.claims[1].mentioned_company == "AAPL"


def test_claim_extractor_claim_typing():
    extractor = ClaimExtractor()
    t1 = "Total revenue was $100 billion [E1]."
    t2 = "Revenue increased compared to the prior fiscal year [E1]."
    t3 = "The company maintained its strategic market presence."

    r1 = extractor.extract_claims(t1)
    r2 = extractor.extract_claims(t2)
    r3 = extractor.extract_claims(t3)

    assert r1.claims[0].claim_type == ClaimType.FINANCIAL_METRIC
    assert r2.claims[0].claim_type == ClaimType.HISTORICAL_COMPARISON
    assert r3.claims[0].claim_type in (
        ClaimType.GENERAL_FACT,
        ClaimType.PERFORMANCE_STATEMENT,
    )


def test_claim_extractor_empty_and_whitespace():
    extractor = ClaimExtractor()
    r = extractor.extract_claims("   \n\n   ")
    assert len(r.claims) == 0
