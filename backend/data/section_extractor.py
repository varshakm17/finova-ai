"""Filing Section Extractor.

Extracts core financial disclosure sections (Item 1, 1A, 7, 7A) from SEC 10-K and 10-Q filings,
distinguishing substantive body sections from Table of Contents listings and inline citations.
"""

import re
from dataclasses import dataclass

from backend.utils.logger import get_logger

logger = get_logger("section_extractor")


@dataclass
class ExtractedSection:
    """Represents an extracted disclosure section from an SEC filing."""

    section_identifier: str  # e.g., 'ITEM_1A', 'ITEM_7', 'ITEM_7A', 'ITEM_1'
    section_title: str  # Canonical heading
    status: str  # 'extracted', 'not_found', 'uncertain'
    text: str
    char_count: int
    start_char: int
    end_char: int


# Section specifications with regex patterns for start and end boundaries
SECTION_SPECS_10K = [
    {
        "id": "ITEM_1",
        "title": "Item 1. Business",
        "start_patterns": [
            r"(?:^|\n)[ \t]*(?:PART\s+I[\.\:\-\s]+)?ITEM\s+1[\.\:\-\s]+BUSINESS(?!\s+ACQUISITIONS?)(?:[^\n]*)",
        ],
        "end_patterns": [
            r"(?:^|\n)[ \t]*ITEM\s+1A[\.\:\-\s]+RISK\s+FACTORS",
            r"(?:^|\n)[ \t]*ITEM\s+1B[\.\:\-\s]+UNRESOLVED",
            r"(?:^|\n)[ \t]*ITEM\s+2[\.\:\-\s]+PROPERTIES",
        ],
    },
    {
        "id": "ITEM_1A",
        "title": "Item 1A. Risk Factors",
        "start_patterns": [
            r"(?:^|\n)[ \t]*(?:PART\s+I[\.\:\-\s]+)?ITEM\s+1A[\.\:\-\s]+RISK\s+FACTORS(?:[^\n]*)",
        ],
        "end_patterns": [
            r"(?:^|\n)[ \t]*ITEM\s+1B[\.\:\-\s]+UNRESOLVED",
            r"(?:^|\n)[ \t]*ITEM\s+1C[\.\:\-\s]+CYBERSECURITY",
            r"(?:^|\n)[ \t]*ITEM\s+2[\.\:\-\s]+PROPERTIES",
        ],
    },
    {
        "id": "ITEM_7",
        "title": "Item 7. Management's Discussion and Analysis",
        "start_patterns": [
            r"(?:^|\n)[ \t]*(?:PART\s+II[\.\:\-\s]+)?ITEM\s+7[\.\:\-\s]+MANAGEMENT['’]?S\s+DISCUSSION\s+AND\s+ANALYSIS(?:[^\n]*)",
        ],
        "end_patterns": [
            r"(?:^|\n)[ \t]*ITEM\s+7A[\.\:\-\s]+QUANTITATIVE\s+AND\s+QUALITATIVE",
            r"(?:^|\n)[ \t]*ITEM\s+8[\.\:\-\s]+FINANCIAL\s+STATEMENTS",
        ],
    },
    {
        "id": "ITEM_7A",
        "title": "Item 7A. Quantitative and Qualitative Disclosures About Market Risk",
        "start_patterns": [
            r"(?:^|\n)[ \t]*(?:PART\s+II[\.\:\-\s]+)?ITEM\s+7A[\.\:\-\s]+QUANTITATIVE\s+AND\s+QUALITATIVE\s+DISCLOSURES(?:[^\n]*)",
        ],
        "end_patterns": [
            r"(?:^|\n)[ \t]*ITEM\s+8[\.\:\-\s]+FINANCIAL\s+STATEMENTS",
            r"(?:^|\n)[ \t]*ITEM\s+9[\.\:\-\s]+CHANGES\s+IN",
        ],
    },
]

# Section specifications for Form 10-Q (different item numbering)
SECTION_SPECS_10Q = [
    {
        "id": "ITEM_7",  # Maps 10-Q MD&A to canonical ITEM_7
        "title": "Part I Item 2. Management's Discussion and Analysis",
        "start_patterns": [
            r"(?:^|\n)[ \t]*(?:PART\s+I[,\s]+)?ITEM\s+2[\.\:\-\s]+MANAGEMENT['’]?S\s+DISCUSSION\s+AND\s+ANALYSIS(?:[^\n]*)",
        ],
        "end_patterns": [
            r"(?:^|\n)[ \t]*(?:PART\s+I[,\s]+)?ITEM\s+3[\.\:\-\s]+QUANTITATIVE\s+AND\s+QUALITATIVE",
            r"(?:^|\n)[ \t]*(?:PART\s+I[,\s]+)?ITEM\s+4[\.\:\-\s]+CONTROLS\s+AND\s+PROCEDURES",
            r"(?:^|\n)[ \t]*PART\s+II",
        ],
    },
    {
        "id": "ITEM_7A",  # Maps 10-Q Market Risk to canonical ITEM_7A
        "title": "Part I Item 3. Quantitative and Qualitative Disclosures About Market Risk",
        "start_patterns": [
            r"(?:^|\n)[ \t]*(?:PART\s+I[,\s]+)?ITEM\s+3[\.\:\-\s]+QUANTITATIVE\s+AND\s+QUALITATIVE\s+DISCLOSURES(?:[^\n]*)",
        ],
        "end_patterns": [
            r"(?:^|\n)[ \t]*(?:PART\s+I[,\s]+)?ITEM\s+4[\.\:\-\s]+CONTROLS\s+AND\s+PROCEDURES",
            r"(?:^|\n)[ \t]*PART\s+II",
        ],
    },
    {
        "id": "ITEM_1A",  # Maps 10-Q Part II Item 1A to canonical ITEM_1A
        "title": "Part II Item 1A. Risk Factors",
        "start_patterns": [
            r"(?:^|\n)[ \t]*(?:PART\s+II[,\s]+)?ITEM\s+1A[\.\:\-\s]+RISK\s+FACTORS(?:[^\n]*)",
        ],
        "end_patterns": [
            r"(?:^|\n)[ \t]*(?:PART\s+II[,\s]+)?ITEM\s+(?:2|3|4|5|6)[\.\:\-\s]+",
            r"(?:^|\n)[ \t]*SIGNATURES",
        ],
    },
]


class SectionExtractor:
    """Extracts prioritized business and financial disclosure sections from parsed filing text."""

    def __init__(self, min_section_chars: int = 150) -> None:
        self.min_section_chars = min_section_chars

    def extract_sections(
        self, text: str, form_type: str = "10-K"
    ) -> list[ExtractedSection]:
        """Extract all supported canonical sections from document text.

        Args:
            text: Parsed filing text.
            form_type: Filing form type ('10-K' or '10-Q').

        Returns:
            list[ExtractedSection]: Extracted sections with status and boundaries.
        """
        if not text or not text.strip():
            return []

        specs = (
            SECTION_SPECS_10Q
            if form_type.upper().startswith("10-Q")
            else SECTION_SPECS_10K
        )
        results: list[ExtractedSection] = []

        for spec in specs:
            extracted = self._extract_single_section(text, spec)
            results.append(extracted)

        return results

    def _extract_single_section(self, text: str, spec: dict) -> ExtractedSection:
        """Locate start and end boundaries for a single section specification, avoiding TOC matches."""
        sec_id = spec["id"]
        sec_title = spec["title"]

        # 1. Find all candidate start positions
        start_matches: list[re.Match] = []
        for pattern in spec["start_patterns"]:
            start_matches.extend(re.finditer(pattern, text, re.IGNORECASE))

        if not start_matches:
            logger.info(
                "Section '%s' (%s) not found in document text", sec_id, sec_title
            )
            return ExtractedSection(
                section_identifier=sec_id,
                section_title=sec_title,
                status="not_found",
                text="",
                char_count=0,
                start_char=-1,
                end_char=-1,
            )

        # Sort matches by character offset
        start_matches.sort(key=lambda m: m.start())

        # 2. Compile end patterns
        combined_end_regex = "|".join(f"(?:{p})" for p in spec["end_patterns"])

        best_candidate: tuple[int, int, str] | None = None

        # 3. Evaluate each start match to bypass Table of Contents entries
        for match in start_matches:
            start_pos = match.end()
            remaining_text = text[start_pos:]

            end_match = re.search(combined_end_regex, remaining_text, re.IGNORECASE)
            if end_match:
                end_pos = start_pos + end_match.start()
                candidate_text = text[start_pos:end_pos].strip()
            else:
                # If no end boundary is matched, take up to 300,000 characters or end of text
                end_pos = min(len(text), start_pos + 300000)
                candidate_text = text[start_pos:end_pos].strip()

            char_length = len(candidate_text)

            # Heuristic: TOC listings are tightly spaced (usually < 200 characters to next item)
            # A real substantive section contains at least min_section_chars characters
            if char_length >= self.min_section_chars:
                # We found a substantive body match
                best_candidate = (start_pos, end_pos, candidate_text)
                break

        if best_candidate:
            start_pos, end_pos, clean_text = best_candidate
            logger.info(
                "Extracted section '%s' (%d characters, offset %d-%d)",
                sec_id,
                len(clean_text),
                start_pos,
                end_pos,
            )
            return ExtractedSection(
                section_identifier=sec_id,
                section_title=sec_title,
                status="extracted",
                text=clean_text,
                char_count=len(clean_text),
                start_char=start_pos,
                end_char=end_pos,
            )

        # If candidates were found but all were under min_section_chars (e.g. only TOC entries)
        logger.warning(
            "Section '%s' matched headings but all candidates were too short (likely TOC-only)",
            sec_id,
        )
        return ExtractedSection(
            section_identifier=sec_id,
            section_title=sec_title,
            status="uncertain",
            text="",
            char_count=0,
            start_char=-1,
            end_char=-1,
        )
