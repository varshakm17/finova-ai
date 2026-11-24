"""Claim Extractor for Anti-Hallucination & Answer Verification.

Deconstructs generated financial research answers into independently verifiable
atomic assertions, extracting numeric entities, reporting periods, company references,
and statutory citations while avoiding naive period splitting on abbreviations.
"""

from __future__ import annotations

import re

from backend.verification.verification_models import (
    ClaimExtractionResult,
    ClaimType,
    ExtractedClaim,
    NumericClaimValue,
)

# Common abbreviations and financial abbreviations that should not trigger sentence boundaries
ABBREVIATIONS = (
    r"(?:inc|corp|ltd|co|u\.s|sec|approx|vs|e\.g|i\.e|no|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
    r"|q1|q2|q3|q4|fy\d{2,4})"
)
ABBR_PATTERN = re.compile(rf"\b{ABBREVIATIONS}\.", re.IGNORECASE)

# Citation pattern: [E1], [C2], [E1, E2]
CITATION_TAG_PATTERN = re.compile(r"\[([EC]\d+(?:\s*,\s*[EC]\d+)*)\]", re.IGNORECASE)
SINGLE_CITATION_PATTERN = re.compile(r"\b([EC]\d+)\b", re.IGNORECASE)

# Numerical entity pattern: matches $120.50 billion, 30.13%, 1.45x, $383,285 million, -5.2%
NUMERIC_PATTERN = re.compile(
    r"(\$?\s*[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|\$?\s*[-+]?\d+(?:\.\d+)?)\s*"
    r"(%|(?:trillion|billion|million|thousand|percent|bps|x)\b)?",
    re.IGNORECASE,
)

# Period extraction patterns: FY2023, FY 2023, 2023, Q3 2023, third quarter of 2023, 2023-09-30
PERIOD_PATTERNS = [
    re.compile(r"\b(FY\s*\d{4})\b", re.IGNORECASE),
    re.compile(r"\b(Q[1-4]\s*(?:FY)?\s*\d{4})\b", re.IGNORECASE),
    re.compile(
        r"\b((?:first|second|third|fourth)\s+quarter(?:\s+of)?\s+\d{4})\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),
    re.compile(r"\b(fiscal\s+(?:year\s+)?\d{4})\b", re.IGNORECASE),
    re.compile(r"\b(calendar\s+(?:year\s+)?\d{4})\b", re.IGNORECASE),
    re.compile(r"\b(19\d{2}|20\d{2})\b"),
]

# Scale factor mapping
SCALE_FACTORS = {
    "trillion": 1e12,
    "billion": 1e9,
    "million": 1e6,
    "thousand": 1e3,
}

# Metric keyword triggers
METRIC_KEYWORDS = {
    "revenue": "revenue",
    "sales": "revenue",
    "gross margin": "gross_margin",
    "operating margin": "operating_margin",
    "operating income": "operating_income",
    "net margin": "net_margin",
    "net income": "net_income",
    "current ratio": "current_ratio",
    "quick ratio": "quick_ratio",
    "debt-to-equity": "debt_to_equity",
    "debt to equity": "debt_to_equity",
    "free cash flow": "free_cash_flow",
    "return on assets": "return_on_assets",
    "return on equity": "return_on_equity",
}

COMPARISON_TRIGGERS = [
    "compared to",
    "increased by",
    "decreased by",
    "rose from",
    "fell from",
    "year-over-year",
    "yoy",
    "higher than",
    "lower than",
    "expanded from",
    "contracted from",
]

RISK_TRIGGERS = [
    "risk",
    "uncertainty",
    "volatility",
    "litigation",
    "regulatory",
    "supply chain",
    "dependency",
    "headwind",
    "adverse",
    "competition",
]


class ClaimExtractor:
    """Extracts atomic, verifiable assertions and entities from answer text."""

    def __init__(self) -> None:
        pass

    def segment_sentences(self, text: str) -> list[str]:
        """Split text into sentences while protecting abbreviations, numbers, and brackets."""
        if not text or not text.strip():
            return []

        # Step 1: Normalize carriage returns and protect known abbreviations
        cleaned = text.replace("\r\n", "\n").replace("\r", "\n")

        # Replace dots in known abbreviations with a placeholder
        def mask_abbr(match: re.Match[str]) -> str:
            return match.group(0).replace(".", "@@DOT@@")

        masked = ABBR_PATTERN.sub(mask_abbr, cleaned)

        # Protect decimals between digits like 120.50
        masked = re.sub(r"(\d)\.(\d)", r"\1@@DOT@@\2", masked)

        # Protect citations: e.g. [E1]
        def mask_brackets(match: re.Match[str]) -> str:
            return match.group(0).replace(".", "@@DOT@@")

        masked = re.sub(r"\[[^\]]+\]", mask_brackets, masked)

        # Step 2: Split by bullet points, newlines, and unmasked sentence terminators (. ! ?)
        lines = masked.split("\n")
        raw_sentences: list[str] = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip markdown table rows, table separators, headers, horizontal dividers
            if line.startswith(("#", "===", "---")) or line.startswith("|") or re.match(r"^\|?[\s\-:|]+\|?$", line):
                continue

            # Skip document metadata lines and non-assertion meta statements
            if re.match(r"^\*{0,2}(?:Reporting Period|Generated|Verification Status|System|Research Objective):", line, re.IGNORECASE):
                continue
            if "zero llm arithmetic is employed" in line.lower() or (line.startswith("Retrieved ") and "evidence passages" in line):
                continue

            # Strip bullet prefixes like "- ", "* ", "1. "
            line = re.sub(r"^(?:[-*•]|\d+[\.)])\s*", "", line)
            if not line:
                continue

            # Skip reference lines like **[E1]**: SEC Form... or **[C1]**: Deterministic...
            if re.match(r"^\*{0,2}\[[EC]\d+\]\*{0,2}:", line, re.IGNORECASE):
                continue

            # Extract bullet citation if present
            bullet_cites = re.findall(r"\[([EC]\d+)\]", line, re.IGNORECASE)

            # Split on sentence terminals
            parts = re.split(r"(?<=[.!?])\s+", line)
            for part in parts:
                p = part.strip()
                if p:
                    # Unmask placeholders
                    unmasked = p.replace("@@DOT@@", ".")
                    if len(unmasked.split()) < 2:
                        continue
                    # Propagate bullet citation to sentences within the bullet
                    if bullet_cites and not re.search(r"\[[EC]\d+\]", unmasked):
                        unmasked = f"{unmasked} [{bullet_cites[0]}]"
                    raw_sentences.append(unmasked)

        return raw_sentences

    def parse_numeric_entities(self, text: str) -> list[NumericClaimValue]:
        """Extract quantitative entities and scale multipliers from text."""
        entities: list[NumericClaimValue] = []

        for match in NUMERIC_PATTERN.finditer(text):
            raw_val_str = match.group(1).strip()
            unit_str = match.group(2).lower() if match.group(2) else None

            # Skip if immediately preceded by FY, Q, or fiscal
            start_pos = match.start(1)
            prefix = text[max(0, start_pos - 6) : start_pos].lower()
            if prefix.endswith("fy") or prefix.endswith("q") or "fiscal" in prefix:
                continue

            # Skip date components like YYYY-MM-DD or YYYY-MM (e.g., 2023-11-03 or 2023-11)
            date_prefix = text[max(0, start_pos - 10) : start_pos]
            if re.search(r"\b\d{4}-$", date_prefix) or re.search(r"\b\d{4}-\d{2}-$", date_prefix):
                continue

            # Skip statutory structural indicators like Item 8, Item 7, Note 3, Form 10, Part 2
            prefix_lower = text[max(0, start_pos - 15) : start_pos].lower().strip()
            if any(prefix_lower.endswith(sec_prefix) for sec_prefix in ["item", "part", "note", "form", "section"]):
                continue

            # Skip Form 10-K, 10-Q references
            post_str = text[match.end() : match.end() + 5].lower().strip()
            if post_str.startswith("-k") or post_str.startswith("-q"):
                continue

            # Ignore pure year tokens like 2022, 2023 if not preceded by $ or followed by financial unit
            clean_digits = raw_val_str.replace("$", "").replace(",", "").strip()
            try:
                val = float(clean_digits)
            except ValueError:
                continue

            # Skip standalone 4-digit years (e.g. 2023) if no currency sign and no unit
            if not raw_val_str.startswith("$") and unit_str is None:
                if 1980 <= val <= 2050 and "." not in clean_digits:
                    continue

            is_percent = unit_str in {"%", "percent", "bps"} or "%" in raw_val_str
            scale = 1.0
            if unit_str in SCALE_FACTORS:
                scale = SCALE_FACTORS[unit_str]
            elif raw_val_str.startswith("$"):
                unit_str = "USD"

            normalized = val * scale if not is_percent else val

            # Infer metric from sentence context
            metric_hint = None
            t_lower = text.lower()
            for kw, mname in METRIC_KEYWORDS.items():
                if kw in t_lower:
                    metric_hint = mname
                    break

            entities.append(
                NumericClaimValue(
                    raw_text=match.group(0).strip(),
                    numeric_value=val,
                    unit=unit_str,
                    metric_name=metric_hint,
                    scale_multiplier=scale,
                    normalized_value=normalized,
                    is_percentage=is_percent,
                )
            )

        return entities

    def extract_period(self, text: str) -> str | None:
        """Extract canonical fiscal or calendar reporting period mentioned in text."""
        for pattern in PERIOD_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group(1).strip()
        return None

    def extract_company(self, text: str) -> str | None:
        """Extract referenced company ticker or entity name."""
        # 1. Match prominent company names first
        for name in [
            "Apple",
            "Microsoft",
            "Alphabet",
            "Google",
            "Amazon",
            "NVIDIA",
            "Meta",
            "Tesla",
        ]:
            if name.lower() in text.lower():
                return name

        # 2. Match known corporate stock tickers
        known_tickers = {
            "AAPL",
            "MSFT",
            "TSLA",
            "NVDA",
            "AMZN",
            "GOOG",
            "GOOGL",
            "META",
        }
        for token in re.findall(r"\b[A-Z]{2,5}\b", text):
            if token in known_tickers:
                return token

        return None

    def classify_claim_type(
        self,
        text: str,
        numeric_values: list[NumericClaimValue],
    ) -> ClaimType:
        """Determine structural category of an assertion."""
        t_lower = text.lower()

        for trig in COMPARISON_TRIGGERS:
            if trig in t_lower:
                return ClaimType.HISTORICAL_COMPARISON

        if any(trig in t_lower for trig in RISK_TRIGGERS):
            return ClaimType.RISK_OR_BUSINESS

        if numeric_values or any(kw in t_lower for kw in METRIC_KEYWORDS):
            return ClaimType.FINANCIAL_METRIC

        if any(
            w in t_lower
            for w in [
                "performance",
                "profitability",
                "growth",
                "margin",
                "liquidity",
                "expanded",
                "declined",
            ]
        ):
            return ClaimType.PERFORMANCE_STATEMENT

        return ClaimType.GENERAL_FACT

    def extract_claims(
        self,
        text: str,
        answer_id: str = "ans_default",
    ) -> ClaimExtractionResult:
        """Deconstruct answer text into atomic claims with entities and citations."""
        sentences = self.segment_sentences(text)
        extracted: list[ExtractedClaim] = []

        for idx, sentence in enumerate(sentences, start=1):
            claim_id = f"CLM-{idx:02d}"

            # Extract citations in this sentence
            citations: list[str] = []
            tag_matches = CITATION_TAG_PATTERN.findall(sentence)
            for tm in tag_matches:
                for part in SINGLE_CITATION_PATTERN.findall(tm):
                    c_id = part.upper()
                    if c_id not in citations:
                        citations.append(c_id)

            # Strip citation tags from clean claim text for verification
            clean_claim_text = CITATION_TAG_PATTERN.sub("", sentence).strip()
            # Clean up double spaces or dangling punctuation
            clean_claim_text = re.sub(r"\s+", " ", clean_claim_text).strip()

            numeric_entities = self.parse_numeric_entities(clean_claim_text)
            period = self.extract_period(clean_claim_text)
            company = self.extract_company(clean_claim_text)
            claim_type = self.classify_claim_type(clean_claim_text, numeric_entities)

            # Determine whether objectively verifiable
            # Meta statements like "Sources used:", "In summary:" are not verifiable
            is_verifiable = True
            c_lower = clean_claim_text.lower()
            if (
                len(clean_claim_text.split()) < 3
                or c_lower.startswith("sources used")
                or c_lower.startswith("in conclusion")
                or c_lower.startswith("grounded answer")
                or "sufficient evidence" in c_lower
                or c_lower.startswith("this executive research brief")
                or c_lower.startswith("business profile:")
                or c_lower.startswith("all financial metrics")
                or c_lower.startswith("longitudinal comparison")
                or c_lower.startswith("analysis of operational")
                or c_lower.startswith("statutory disclosures from")
                or c_lower.startswith("synthesis of core evidence")
                or c_lower.startswith("statutory sec filings")
                or c_lower.startswith("research objective:")
                or c_lower.startswith("financial calculations yielded")
                or c_lower.startswith("longitudinal analysis identified")
                or (c_lower.startswith("identified ") and "risk factors" in c_lower)
                or (clean_claim_text.startswith("**") and any(d in clean_claim_text for d in ["(EXPANDING)", "(CONTRACTING)", "(MIXED)", "(STABLE)", "(UPWARD)", "(DOWNWARD)", "(GROWING)", "(DECLINING)"]))
                or "demonstrated mixed volatility across periods" in c_lower
                or "operates within statutory reporting guidelines" in c_lower
                or c_lower.startswith("_no specific")
                or c_lower.startswith("no specific")
            ):
                is_verifiable = False

            extracted.append(
                ExtractedClaim(
                    claim_id=claim_id,
                    claim_text=clean_claim_text,
                    claim_type=claim_type,
                    numeric_values=numeric_entities,
                    mentioned_company=company,
                    mentioned_period=period,
                    citation_ids=citations,
                    is_verifiable=is_verifiable,
                )
            )

        return ClaimExtractionResult(
            answer_id=answer_id,
            original_text=text,
            claims=extracted,
            extraction_method="deterministic_rule_based",
        )
