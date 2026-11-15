"""Dense Semantic Search Engine for Corporate Financial Filings.

Executes vector similarity search over SEC filing document chunks using
normalized cosine similarity, resolves vector IDs to rich statutory metadata,
applies company/filing/section filters, and guarantees full source provenance.
"""

from backend.data.document_storage import DocumentStorage
from backend.retrieval.embedding_service import EmbeddingService
from backend.retrieval.retrieval_models import SemanticSearchResult
from backend.retrieval.vector_store import BaseVectorStore, get_vector_store
from backend.utils.logger import get_logger
from config.settings import Settings, get_settings

logger = get_logger("semantic_search")


class SemanticSearchService:
    """Provides semantic search over indexed document chunks with provenance resolution."""

    def __init__(
        self,
        document_storage: DocumentStorage | None = None,
        embedding_service: EmbeddingService | None = None,
        vector_store: BaseVectorStore | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.doc_storage = document_storage or DocumentStorage()
        self.embedding_service = embedding_service or EmbeddingService(
            settings=self.settings
        )
        self.vector_store = vector_store or get_vector_store(
            backend=self.settings.EMBEDDING_BACKEND,
            dimension=self.embedding_service.get_embedding_dimension(),
            index_dir=self.settings.EMBEDDING_INDEX_DIR,
        )

    def search(
        self,
        query: str,
        ticker: str | None = None,
        filing_type: str | None = None,
        section_identifier: str | None = None,
        top_k: int = 5,
        similarity_threshold: float = 0.0,
    ) -> list[SemanticSearchResult]:
        """Perform dense semantic search over indexed document chunks.

        Args:
            query: Natural-language search query.
            ticker: Optional ticker symbol filter.
            filing_type: Optional filing type filter (e.g. '10-K', '10-Q').
            section_identifier: Optional section filter (e.g. 'ITEM_1A', 'ITEM_7').
            top_k: Maximum number of ranked results to return (1-50).
            similarity_threshold: Minimum cosine similarity score [-1.0, 1.0].

        Returns:
            list[SemanticSearchResult]: Ranked search results with source provenance.

        Raises:
            ValueError: If query is empty or whitespace-only.
        """
        if not query or not query.strip():
            raise ValueError("Search query cannot be empty or whitespace-only.")

        stats = self.vector_store.get_index_stats()
        if stats.get("total_vectors", 0) == 0:
            logger.debug("Vector index is empty. Returning 0 search results.")
            return []

        # 1. Encode user query into normalized 1D vector
        query_vector = self.embedding_service.encode_query(query.strip())

        # 2. Determine over-fetch multiplier if post-filtering by metadata
        has_filters = bool(ticker or filing_type or section_identifier)
        total_in_index = stats.get("total_vectors", 0)
        if has_filters:
            fetch_k = min(total_in_index, max(top_k * 10, 50))
        else:
            fetch_k = min(total_in_index, top_k)

        # 3. Retrieve raw vector matches sorted by descending cosine similarity
        raw_matches = self.vector_store.search(query_vector=query_vector, top_k=fetch_k)

        results: list[SemanticSearchResult] = []
        clean_ticker = ticker.strip().upper() if ticker else None
        clean_filing = filing_type.strip().upper() if filing_type else None
        clean_section = (
            section_identifier.strip().upper() if section_identifier else None
        )

        # 4. Resolve vector IDs through SQLite metadata and apply filters
        for chunk_id, sim_score in raw_matches:
            if sim_score < similarity_threshold:
                continue

            chunk_meta = self.doc_storage.get_chunk_with_provenance(chunk_id)
            if not chunk_meta:
                logger.debug(
                    "Chunk ID %s found in index but missing in SQLite; skipping.",
                    chunk_id,
                )
                continue

            # Metadata filtering
            if clean_ticker and chunk_meta["ticker"].upper() != clean_ticker:
                continue

            if clean_filing and chunk_meta["filing_type"].upper() != clean_filing:
                continue

            if (
                clean_section
                and chunk_meta["section_identifier"].upper() != clean_section
            ):
                continue

            result = SemanticSearchResult(
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
                similarity_score=round(float(sim_score), 4),
                source_url=chunk_meta["source_url"],
            )
            results.append(result)

            if len(results) >= top_k:
                break

        return results
