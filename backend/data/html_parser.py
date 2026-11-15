"""SEC Filing HTML Document Parser.

Extracts clean, readable text from SEC EDGAR HTML and inline XBRL documents,
preserving structural headings, paragraphs, and financial disclosure tables
while stripping non-content markup.
"""

import re

from bs4 import BeautifulSoup, Comment

from backend.utils.logger import get_logger

logger = get_logger("html_parser")

# Non-content tags to strip completely
STRIP_TAGS = {"script", "style", "noscript", "meta", "link", "head", "iframe", "svg"}
INLINE_TAGS = {
    "span",
    "font",
    "b",
    "strong",
    "i",
    "em",
    "u",
    "a",
    "small",
    "sub",
    "sup",
}
BLOCK_TAGS = ["p", "h1", "h2", "h3", "h4", "h5", "h6", "div", "li", "hr"]


class HTMLDocumentParser:
    """Parser for SEC statutory filing HTML documents."""

    def __init__(self) -> None:
        pass

    def parse_html(self, html_content: str | bytes) -> str:
        """Parse SEC filing HTML and convert to clean, structured text.

        Args:
            html_content: Raw HTML content as string or bytes.

        Returns:
            str: Normalized, readable text preserving section and table boundaries.
        """
        if not html_content:
            return ""

        try:
            # BeautifulSoup with standard html.parser for zero C-extension dependencies
            soup = BeautifulSoup(html_content, "html.parser")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Error initializing BeautifulSoup on HTML: %s. Using fallback regex.",
                exc,
            )
            return self._fallback_clean(str(html_content))

        # 1. Remove comments
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        # 2. Remove script, style, noscript, etc.
        for tag_name in STRIP_TAGS:
            for element in soup.find_all(tag_name):
                element.decompose()

        # 3. Remove elements explicitly marked as hidden (by style, attribute, or class)
        for hidden in soup.find_all(
            lambda tag: (
                tag.get("hidden") is not None
                or tag.get("aria-hidden") == "true"
                or (
                    tag.get("class")
                    and any("hidden" in c.lower() for c in tag.get("class", []))
                )
                or (
                    tag.get("style")
                    and re.search(
                        r"display\s*:\s*none", tag.get("style", ""), re.IGNORECASE
                    )
                )
            )
        ):
            hidden.decompose()

        # 4. Format tables to preserve row and cell structure
        for table in soup.find_all("table"):
            table_text = self._format_table(table)
            # Replace the table tag with a text node containing formatted rows
            table.replace_with(soup.new_string(f"\n\n{table_text}\n\n"))

        # 5. Handle inline tags and inline XBRL tags (e.g., <ix:nonnumeric>, <ix:nonfraction>)
        # Unwrap inline and inline-XBRL tags so their inner text flows smoothly without line breaks
        for inline in soup.find_all(
            lambda t: t.name in INLINE_TAGS or (t.name and t.name.startswith("ix:"))
        ):
            inline.unwrap()

        # Smooth adjacent text nodes created by unwrapping
        soup.smooth()

        # 6. Ensure block-level elements have whitespace separators
        for br in soup.find_all("br"):
            br.replace_with("\n")

        for block in soup.find_all(BLOCK_TAGS):
            block.append("\n\n")

        # 7. Extract text
        text = soup.get_text()

        # 8. Normalize whitespace
        return self._normalize_text(text)

    def _format_table(self, table: BeautifulSoup) -> str:
        """Format an HTML table into plain text lines with pipe-separated columns.

        Args:
            table: BeautifulSoup table element.

        Returns:
            str: Pipe-formatted table text.
        """
        rows_text: list[str] = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue

            cell_texts: list[str] = []
            for cell in cells:
                c_text = " ".join(cell.get_text().split()).strip()
                if c_text:
                    cell_texts.append(c_text)

            if cell_texts:
                # Format non-empty row
                rows_text.append(" | ".join(cell_texts))

        return "\n".join(rows_text)

    def _normalize_text(self, text: str) -> str:
        """Normalize whitespace, non-breaking spaces, and excessive linebreaks."""
        if not text:
            return ""

        # Replace non-breaking spaces and zero-width spaces
        text = text.replace("\xa0", " ").replace("\u200b", " ").replace("\t", " ")

        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        lines: list[str] = []
        for line in text.split("\n"):
            # Collapse multiple spaces within line
            cleaned_line = re.sub(r"[ ]{2,}", " ", line).strip()
            lines.append(cleaned_line)

        # Recombine lines
        joined = "\n".join(lines)

        # Collapse 3 or more consecutive newlines into exactly 2 (\n\n)
        normalized = re.sub(r"\n{3,}", "\n\n", joined)
        return normalized.strip()

    def _fallback_clean(self, raw_html: str) -> str:
        """Fallback regex cleaning in case of parser crash on malformed HTML."""
        # Strip script and style blocks
        clean = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", raw_html)
        # Strip tags
        clean = re.sub(r"<[^>]+>", " ", clean)
        # Collapse whitespace
        return self._normalize_text(clean)
