"""Section-Aware Text Chunker for Financial Filings.

Splits extracted disclosure sections into deterministic, coherent text chunks
respecting paragraph and sentence boundaries while preserving full filing provenance.
"""

import re
from dataclasses import dataclass

from config.settings import Settings, get_settings


@dataclass
class DocumentChunk:
    """A deterministic text chunk preserving source section and filing metadata."""

    company_ticker: str
    company_cik: str
    company_name: str
    accession_number: str
    filing_type: str
    filing_date: str
    report_date: str
    section_identifier: str
    section_title: str
    chunk_index: int
    source_url: str
    start_offset: int
    end_offset: int
    char_count: int
    chunk_text: str


class SectionChunker:
    """Splits section text into overlapping, boundary-aware chunks."""

    def __init__(
        self,
        settings: Settings | None = None,
        chunk_size: int | None = None,
        overlap: int | None = None,
    ) -> None:
        cfg = settings or get_settings()
        self.chunk_size = chunk_size or cfg.CHUNK_TARGET_SIZE
        self.overlap = overlap or cfg.CHUNK_OVERLAP

        if self.overlap >= self.chunk_size:
            raise ValueError(
                f"Chunk overlap ({self.overlap}) must be smaller than target chunk size ({self.chunk_size})"
            )

    def chunk_section(
        self,
        section_text: str,
        company_ticker: str,
        company_cik: str,
        company_name: str,
        accession_number: str,
        filing_type: str,
        filing_date: str,
        report_date: str,
        section_identifier: str,
        section_title: str,
        source_url: str,
        base_offset: int = 0,
    ) -> list[DocumentChunk]:
        """Split section text into deterministic chunks with complete metadata.

        Args:
            section_text: Plain text of the extracted section.
            company_ticker: Stock ticker.
            company_cik: 10-digit CIK.
            company_name: Corporate name.
            accession_number: Unique filing accession number.
            filing_type: Filing form code (10-K, 10-Q).
            filing_date: Filing acceptance date.
            report_date: Period end report date.
            section_identifier: Section code (e.g., 'ITEM_1A').
            section_title: Section header title.
            source_url: Canonical archive URL.
            base_offset: Character offset of section within parent document.

        Returns:
            list[DocumentChunk]: Ordered, deterministic chunks.
        """
        clean_text = section_text.strip()
        if not clean_text:
            return []

        text_length = len(clean_text)

        # If section is small enough, produce exactly one chunk
        if text_length <= self.chunk_size:
            return [
                DocumentChunk(
                    company_ticker=company_ticker.upper(),
                    company_cik=company_cik,
                    company_name=company_name,
                    accession_number=accession_number,
                    filing_type=filing_type.upper(),
                    filing_date=filing_date,
                    report_date=report_date,
                    section_identifier=section_identifier,
                    section_title=section_title,
                    chunk_index=0,
                    source_url=source_url,
                    start_offset=base_offset,
                    end_offset=base_offset + text_length,
                    char_count=text_length,
                    chunk_text=clean_text,
                )
            ]

        # Multi-chunk splitting
        chunks: list[DocumentChunk] = []
        start_idx = 0
        chunk_idx = 0

        while start_idx < text_length:
            target_end = start_idx + self.chunk_size

            if target_end >= text_length:
                # Last remaining slice
                actual_end = text_length
            else:
                # Find the most natural breakpoint within the trailing 500 characters
                window_start = max(start_idx + self.overlap, target_end - 400)
                window = clean_text[window_start : target_end + 150]

                # 1. Prefer paragraph break (\n\n)
                paragraph_match = [m.end() for m in re.finditer(r"\n\n+", window)]
                if paragraph_match:
                    actual_end = window_start + paragraph_match[-1]
                else:
                    # 2. Prefer sentence boundary (. ! ?)
                    sentence_match = [m.end() for m in re.finditer(r"[.!?]\s+", window)]
                    if sentence_match:
                        actual_end = window_start + sentence_match[-1]
                    else:
                        # 3. Prefer word boundary (whitespace)
                        space_match = [m.end() for m in re.finditer(r"\s+", window)]
                        if space_match:
                            actual_end = window_start + space_match[-1]
                        else:
                            # Hard cutoff fallback
                            actual_end = target_end

            chunk_content = clean_text[start_idx:actual_end].strip()

            if chunk_content:
                chunks.append(
                    DocumentChunk(
                        company_ticker=company_ticker.upper(),
                        company_cik=company_cik,
                        company_name=company_name,
                        accession_number=accession_number,
                        filing_type=filing_type.upper(),
                        filing_date=filing_date,
                        report_date=report_date,
                        section_identifier=section_identifier,
                        section_title=section_title,
                        chunk_index=chunk_idx,
                        source_url=source_url,
                        start_offset=base_offset + start_idx,
                        end_offset=base_offset + actual_end,
                        char_count=len(chunk_content),
                        chunk_text=chunk_content,
                    )
                )
                chunk_idx += 1

            if actual_end >= text_length:
                break

            # Calculate next start position with overlap
            next_start = actual_end - self.overlap

            # Ensure forward progress
            if next_start <= start_idx:
                next_start = start_idx + max(1, self.chunk_size - self.overlap)

            # Align next start to word boundary if possible
            if next_start < text_length and not clean_text[next_start].isspace():
                space_pos = clean_text.find(" ", next_start, next_start + 100)
                if space_pos != -1:
                    next_start = space_pos + 1

            start_idx = next_start

        return chunks
