"""BM25 Sparse Lexical Retrieval Engine for Financial Disclosures.

Implements domain-aware financial tokenization, persistent BM25 indexing
using BM25Okapi, metadata-filtered keyword search, and complete SEC filing provenance.
"""

from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path
from typing import Any

import numpy as np
from rank_bm25 import BM25Okapi

from backend.data.document_storage import DocumentStorage
from backend.retrieval.retrieval_models import BM25SearchResult
from backend.utils.logger import get_logger
from config.settings import Settings, get_settings

logger = get_logger("bm25_search")

# Regex pattern designed for financial disclosures:
# 1. Currency with numbers: $5.2, $1,000, $50
# 2. Percentages: 15.4%, 10%
# 3. Hyphenated financial terms: year-over-year, 10-K, 10-Q, non-GAAP, cash-flow, debt-to-equity
# 4. Standalone numbers, dates, decimals: 2023, 100, 3.14
# 5. Words, acronyms, identifiers: EBITDA, GAAP, revenue, Item_1A
FINANCIAL_TOKEN_PATTERN = re.compile(
    r"\$\d+(?:,\d{3})*(?:\.\d+)?"  # Monetary amounts ($5.2, $1,000)
    r"|\d+(?:\.\d+)?%"  # Percentages (15.4%, 10%)
    r"|[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)+"  # Hyphenated (year-over-year, 10-K)
    r"|\d+(?:,\d{3})*(?:\.\d+)?"  # Numbers and years (2023, 100, 3.14)
    r"|[a-zA-Z0-9_]+",  # Standard words and acronyms (EBITDA, GAAP)
    re.IGNORECASE,
)

# Minimal, safe English function words that never destroy financial signals
FINANCIAL_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "being",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "were",
    "with",
}


class FinancialBM25(BM25Okapi):
    """BM25Okapi variant with smoothed Robertson/Lucene IDF.

    Computes idf = ln(1 + (N - n + 0.5) / (n + 0.5)), guaranteeing strictly positive
    scores across both small corpora and large corpora without negative/zero IDF artifacts.
    """

    def _calc_idf(self, nd: dict[str, int]) -> None:
        for word, freq in nd.items():
            self.idf[word] = math.log(
                1.0 + (self.corpus_size - freq + 0.5) / (freq + 0.5)
            )


class FinancialTokenizer:
    """Deterministic tokenizer preserving financial expressions, symbols, and terminology."""

    def __init__(
        self,
        version: str = "1.0.0",
        remove_stopwords: bool = True,
    ) -> None:
        self.version = version
        self.remove_stopwords = remove_stopwords

    def tokenize(self, text: str) -> list[str]:
        """Tokenize document or query text into normalized lowercase tokens.

        Args:
            text: Raw input text.

        Returns:
            list[str]: Normalized token sequence.
        """
        if not text or not text.strip():
            return []

        # Find all matching tokens
        raw_tokens = FINANCIAL_TOKEN_PATTERN.findall(text)
        tokens: list[str] = []

        for t in raw_tokens:
            clean = t.strip().lower()
            if not clean:
                continue
            if self.remove_stopwords and clean in FINANCIAL_STOPWORDS:
                continue
            tokens.append(clean)

        return tokens

    def tokenize_query(self, query: str) -> list[str]:
        """Tokenize a search query."""
        return self.tokenize(query)


class BM25Index:
    """Manages an in-memory and disk-persisted BM25Okapi lexical index."""

    def __init__(
        self,
        index_dir: Path | str | None = None,
        tokenizer: FinancialTokenizer | None = None,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.index_dir = Path(index_dir) if index_dir else Path("datasets/indexes/bm25")
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.tokenizer = tokenizer or FinancialTokenizer()
        self.k1 = k1
        self.b = b

        self._chunk_ids: list[str] = []
        self._id_to_idx: dict[str, int] = {}
        self._tokenized_corpus: list[list[str]] = []
        self._content_hashes: dict[str, str] = {}
        self._bm25: BM25Okapi | None = None
        self._updated_at: str | None = None

        # Automatically attempt loading existing index
        self.load()

    @property
    def total_chunks(self) -> int:
        """Total document chunks currently in the index."""
        return len(self._chunk_ids)

    def rebuild_bm25_model(self) -> None:
        """Instantiate FinancialBM25 model from current tokenized corpus."""
        if self._tokenized_corpus and len(self._tokenized_corpus) > 0:
            self._bm25 = FinancialBM25(
                corpus=self._tokenized_corpus,
                k1=self.k1,
                b=self.b,
            )
        else:
            self._bm25 = None

    def add_or_update_chunk(
        self,
        chunk_id: str,
        text: str,
        content_hash: str,
    ) -> list[str]:
        """Tokenize and add or update a single chunk in the index corpus.

        Args:
            chunk_id: Unique chunk identifier.
            text: Raw chunk text.
            content_hash: Cryptographic hash of chunk text.

        Returns:
            list[str]: Generated token list.
        """
        clean_id = chunk_id.strip()
        tokens = self.tokenizer.tokenize(text)

        if clean_id in self._id_to_idx:
            idx = self._id_to_idx[clean_id]
            self._tokenized_corpus[idx] = tokens
            self._content_hashes[clean_id] = content_hash
        else:
            idx = len(self._chunk_ids)
            self._chunk_ids.append(clean_id)
            self._id_to_idx[clean_id] = idx
            self._tokenized_corpus.append(tokens)
            self._content_hashes[clean_id] = content_hash

        return tokens

    def remove_chunk(self, chunk_id: str) -> bool:
        """Remove a chunk from the index.

        Args:
            chunk_id: Chunk identifier to remove.

        Returns:
            bool: True if removed, False if not present.
        """
        clean_id = chunk_id.strip()
        if clean_id not in self._id_to_idx:
            return False

        idx = self._id_to_idx[clean_id]
        self._chunk_ids.pop(idx)
        self._tokenized_corpus.pop(idx)
        self._content_hashes.pop(clean_id, None)

        # Rebuild ID index mapping
        self._id_to_idx = {cid: i for i, cid in enumerate(self._chunk_ids)}
        return True

    def build_from_chunks(
        self,
        chunk_data: list[tuple[str, str, str]],
    ) -> None:
        """Build entire BM25 index from a collection of (chunk_id, text, content_hash).

        Args:
            chunk_data: List of tuples (chunk_id, text, content_hash).
        """
        self._chunk_ids = []
        self._id_to_idx = {}
        self._tokenized_corpus = []
        self._content_hashes = {}

        for i, (cid, text, chash) in enumerate(chunk_data):
            clean_id = cid.strip()
            tokens = self.tokenizer.tokenize(text)
            self._chunk_ids.append(clean_id)
            self._id_to_idx[clean_id] = i
            self._tokenized_corpus.append(tokens)
            self._content_hashes[clean_id] = chash

        self.rebuild_bm25_model()
        self._updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.save()

    def search(
        self,
        query_tokens: list[str],
        top_k: int = 50,
    ) -> list[tuple[str, float]]:
        """Compute BM25 Okapi scores for query tokens against the indexed corpus.

        Args:
            query_tokens: Tokenized search query.
            top_k: Maximum number of matches to return.

        Returns:
            list[tuple[str, float]]: Ranked (chunk_id, bm25_score) pairs with score > 0.
        """
        if not self._bm25 or not query_tokens or self.total_chunks == 0 or top_k <= 0:
            return []

        scores: np.ndarray = self._bm25.get_scores(query_tokens)

        # Filter strictly positive matches (query term present in document)
        positive_indices = np.where(scores > 0.0)[0]
        if len(positive_indices) == 0:
            return []

        # Sort indices by descending score
        positive_scores = scores[positive_indices]
        sorted_pos = np.argsort(positive_scores)[::-1]
        sorted_indices = positive_indices[sorted_pos][:top_k]

        return [(self._chunk_ids[i], float(scores[i])) for i in sorted_indices]

    def save(self, target_dir: Path | str | None = None) -> bool:
        """Persist BM25 tokenized corpus, chunk IDs, and metadata to disk safely as JSON.

        Args:
            target_dir: Optional override directory.

        Returns:
            bool: True if save succeeded.
        """
        out_dir = Path(target_dir) if target_dir else self.index_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        ids_path = out_dir / "bm25_index_ids.json"
        corpus_path = out_dir / "bm25_tokenized_corpus.json"
        hashes_path = out_dir / "bm25_hashes.json"
        meta_path = out_dir / "bm25_meta.json"

        try:
            with open(ids_path, "w", encoding="utf-8") as f:
                json.dump(self._chunk_ids, f, indent=2)

            with open(corpus_path, "w", encoding="utf-8") as f:
                json.dump(self._tokenized_corpus, f)

            with open(hashes_path, "w", encoding="utf-8") as f:
                json.dump(self._content_hashes, f, indent=2)

            total_tokens = sum(len(doc) for doc in self._tokenized_corpus)
            avgdl = total_tokens / max(1, len(self._tokenized_corpus))

            meta = {
                "tokenizer_version": self.tokenizer.version,
                "k1": self.k1,
                "b": self.b,
                "total_chunks": len(self._chunk_ids),
                "total_tokens": total_tokens,
                "avg_doc_len": round(avgdl, 2),
                "updated_at": self._updated_at
                or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)

            logger.info(
                "Persisted BM25 index (%d chunks) to %s", len(self._chunk_ids), out_dir
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to persist BM25 index: %s", exc)
            return False

    def load(self, source_dir: Path | str | None = None) -> bool:
        """Load persistent BM25 index components and rebuild BM25Okapi runtime object.

        Args:
            source_dir: Optional source directory.

        Returns:
            bool: True if successfully loaded, False otherwise.
        """
        src_dir = Path(source_dir) if source_dir else self.index_dir
        ids_path = src_dir / "bm25_index_ids.json"
        corpus_path = src_dir / "bm25_tokenized_corpus.json"
        hashes_path = src_dir / "bm25_hashes.json"
        meta_path = src_dir / "bm25_meta.json"

        if not ids_path.exists() or not corpus_path.exists():
            return False

        try:
            with open(ids_path, encoding="utf-8") as f:
                self._chunk_ids = json.load(f)

            with open(corpus_path, encoding="utf-8") as f:
                self._tokenized_corpus = json.load(f)

            if hashes_path.exists():
                with open(hashes_path, encoding="utf-8") as f:
                    self._content_hashes = json.load(f)
            else:
                self._content_hashes = {}

            if meta_path.exists():
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)
                    self._updated_at = meta.get("updated_at")

            self._id_to_idx = {cid: i for i, cid in enumerate(self._chunk_ids)}
            self.rebuild_bm25_model()
            logger.info(
                "Loaded BM25 index with %d chunks from %s",
                len(self._chunk_ids),
                src_dir,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load BM25 index from %s: %s", src_dir, exc)
            return False

    def clear(self) -> None:
        """Clear the in-memory index and delete persistent files."""
        self._chunk_ids = []
        self._id_to_idx = {}
        self._tokenized_corpus = []
        self._content_hashes = {}
        self._bm25 = None
        self._updated_at = None

        for filename in [
            "bm25_index_ids.json",
            "bm25_tokenized_corpus.json",
            "bm25_hashes.json",
            "bm25_meta.json",
        ]:
            p = self.index_dir / filename
            if p.exists():
                try:
                    p.unlink()
                except OSError as exc:
                    logger.warning("Could not delete %s: %s", p, exc)

    def get_stats(self) -> dict[str, Any]:
        """Return diagnostic metrics for the sparse index."""
        vocab: set[str] = set()
        total_tokens = 0
        for doc in self._tokenized_corpus:
            vocab.update(doc)
            total_tokens += len(doc)

        avgdl = total_tokens / max(1, len(self._tokenized_corpus))

        return {
            "total_chunks": len(self._chunk_ids),
            "tokenizer_version": self.tokenizer.version,
            "vocab_size": len(vocab),
            "total_tokens": total_tokens,
            "avg_doc_len": round(avgdl, 2),
            "k1": self.k1,
            "b": self.b,
            "index_dir": str(self.index_dir),
            "last_updated_at": self._updated_at,
        }


class BM25SearchService:
    """Service providing sparse lexical search over document chunks with metadata filtering."""

    def __init__(
        self,
        document_storage: DocumentStorage | None = None,
        bm25_index: BM25Index | None = None,
        tokenizer: FinancialTokenizer | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.doc_storage = document_storage or DocumentStorage()
        self.tokenizer = tokenizer or FinancialTokenizer(
            version=self.settings.BM25_TOKENIZER_VERSION
        )
        self.bm25_index = bm25_index or BM25Index(
            index_dir=self.settings.BM25_INDEX_DIR,
            tokenizer=self.tokenizer,
            k1=self.settings.BM25_K1,
            b=self.settings.BM25_B,
        )

    def search(
        self,
        query: str,
        ticker: str | None = None,
        filing_type: str | None = None,
        section_identifier: str | None = None,
        top_k: int = 5,
    ) -> list[BM25SearchResult]:
        """Execute BM25 lexical search over indexed document chunks.

        Args:
            query: User's keyword or natural-language query.
            ticker: Optional ticker symbol filter.
            filing_type: Optional filing type filter (e.g. '10-K', '10-Q').
            section_identifier: Optional section filter (e.g. 'ITEM_1A', 'ITEM_7').
            top_k: Maximum number of ranked results to return (1-50).

        Returns:
            list[BM25SearchResult]: Ranked search results with source provenance.

        Raises:
            ValueError: If query is empty or whitespace-only.
        """
        if not query or not query.strip():
            raise ValueError("Search query cannot be empty or whitespace-only.")

        if self.bm25_index.total_chunks == 0:
            logger.debug("BM25 index is empty. Returning 0 search results.")
            return []

        # 1. Tokenize query
        query_tokens = self.tokenizer.tokenize_query(query.strip())
        if not query_tokens:
            logger.debug("Query '%s' yielded 0 tokens after preprocessing.", query)
            return []

        # 2. Over-fetch candidates if post-filtering
        has_filters = bool(ticker or filing_type or section_identifier)
        total_in_index = self.bm25_index.total_chunks
        fetch_k = (
            min(total_in_index, max(top_k * 10, 50))
            if has_filters
            else min(total_in_index, top_k * 2)
        )

        # 3. Retrieve raw matches from BM25 index
        raw_matches = self.bm25_index.search(query_tokens=query_tokens, top_k=fetch_k)

        results: list[BM25SearchResult] = []
        clean_ticker = ticker.strip().upper() if ticker else None
        clean_filing = filing_type.strip().upper() if filing_type else None
        clean_section = (
            section_identifier.strip().upper() if section_identifier else None
        )

        query_token_set = set(query_tokens)

        # 4. Resolve chunks from SQLite and apply filters
        for chunk_id, bm25_score in raw_matches:
            chunk_meta = self.doc_storage.get_chunk_with_provenance(chunk_id)
            if not chunk_meta:
                logger.debug(
                    "Chunk ID %s in BM25 index but missing in SQLite; skipping.",
                    chunk_id,
                )
                continue

            # Filtering
            if clean_ticker and chunk_meta["ticker"].upper() != clean_ticker:
                continue

            if clean_filing and chunk_meta["filing_type"].upper() != clean_filing:
                continue

            if (
                clean_section
                and chunk_meta["section_identifier"].upper() != clean_section
            ):
                continue

            # Find matched query terms in chunk
            chunk_tokens = self.tokenizer.tokenize(chunk_meta["chunk_text"])
            matched = sorted(query_token_set.intersection(chunk_tokens))

            results.append(
                BM25SearchResult(
                    chunk_id=chunk_meta["chunk_id"],
                    ticker=chunk_meta["ticker"],
                    company_name=chunk_meta["company_name"],
                    cik=chunk_meta["cik"],
                    filing_type=chunk_meta["filing_type"],
                    filing_date=chunk_meta["filing_date"],
                    report_date=chunk_meta.get("report_date"),
                    accession_number=chunk_meta["accession_number"],
                    section_identifier=chunk_meta["section_identifier"],
                    section_title=chunk_meta["section_title"],
                    chunk_text=chunk_meta["chunk_text"],
                    bm25_score=round(float(bm25_score), 4),
                    source_url=chunk_meta["source_url"],
                    matched_terms=matched,
                )
            )

            if len(results) >= top_k:
                break

        return results
