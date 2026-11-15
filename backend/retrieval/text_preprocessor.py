"""Text Preprocessor for Semantic Financial Embeddings.

Prepares raw statutory SEC filing text chunks for embedding models.
Normalizes whitespace without degrading financial numbers, percentages,
table delimiters, currency signs, or statutory disclosure terminology.
"""

import hashlib
import re


class TextPreprocessor:
    """Prepares and contextualizes document chunk texts for dense vector embedding."""

    @staticmethod
    def clean_text(text: str) -> str:
        """Normalize whitespace while strictly preserving financial and numerical tokens.

        - Preserves table pipe delimiters (`|`).
        - Preserves monetary values, percentages, negative numbers, and fiscal periods.
        - Collapses horizontal whitespace (spaces, tabs) into a single space.
        - Collapses 3+ consecutive line breaks into standard double newlines (`\n\n`).
        - Strips extraneous leading and trailing whitespace.

        Args:
            text: Raw input text from document chunk.

        Returns:
            str: Cleaned text suitable for language model tokenization.
        """
        if not text:
            return ""

        # Normalize non-standard space characters (non-breaking spaces, zero-width spaces)
        cleaned = text.replace("\u00a0", " ").replace("\u200b", "")

        # Collapse horizontal tabs and repeated spaces into single space per line
        lines = cleaned.splitlines()
        normalized_lines: list[str] = []
        for line in lines:
            # Collapse multiple spaces and tabs into a single space
            norm_line = re.sub(r"[ \t]+", " ", line).strip()
            normalized_lines.append(norm_line)

        # Join lines and collapse excessive consecutive blank lines (max 2 consecutive newlines)
        rejoined = "\n".join(normalized_lines)
        cleaned_text = re.sub(r"\n{3,}", "\n\n", rejoined).strip()
        return cleaned_text

    @classmethod
    def prepare_chunk_text(
        cls,
        chunk_text: str,
        ticker: str | None = None,
        filing_type: str | None = None,
        section_title: str | None = None,
        include_context: bool = True,
    ) -> str:
        """Prepare chunk text for embedding with optional context prefix metadata.

        Embedding input format:
        `Company: AAPL | Filing: 10-K | Section: Risk Factors | Content: [cleaned chunk text]`

        Args:
            chunk_text: Raw chunk text.
            ticker: Company stock ticker symbol (e.g. 'AAPL').
            filing_type: Filing type (e.g. '10-K', '10-Q').
            section_title: Canonical section title (e.g. 'Risk Factors').
            include_context: Whether to prepend the contextual metadata header.

        Returns:
            str: Context-enriched, cleaned text for embedding model input.
        """
        cleaned = cls.clean_text(chunk_text)
        if not cleaned:
            return ""

        if not include_context:
            return cleaned

        header_parts: list[str] = []
        if ticker:
            header_parts.append(f"Company: {ticker.upper().strip()}")
        if filing_type:
            header_parts.append(f"Filing: {filing_type.upper().strip()}")
        if section_title:
            header_parts.append(f"Section: {section_title.strip()}")

        if header_parts:
            context_prefix = " | ".join(header_parts)
            return f"{context_prefix} | Content: {cleaned}"

        return cleaned

    @staticmethod
    def compute_text_hash(text: str) -> str:
        """Compute SHA-256 hash of raw or cleaned text to track content changes."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @classmethod
    def compute_input_hash(
        cls,
        chunk_text: str,
        ticker: str | None = None,
        filing_type: str | None = None,
        section_title: str | None = None,
        include_context: bool = True,
    ) -> str:
        """Compute SHA-256 hash of the fully prepared embedding input."""
        prepared = cls.prepare_chunk_text(
            chunk_text=chunk_text,
            ticker=ticker,
            filing_type=filing_type,
            section_title=section_title,
            include_context=include_context,
        )
        return cls.compute_text_hash(prepared)
