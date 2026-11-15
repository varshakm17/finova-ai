"""Integration tests for SemanticSearchService."""

from pathlib import Path

import pytest

from backend.data.document_storage import DocumentStorage
from backend.data.storage import Database
from backend.retrieval.embedding_service import EmbeddingService
from backend.retrieval.indexing_service import IndexingService
from backend.retrieval.semantic_search import SemanticSearchService
from backend.retrieval.vector_store import NumpyVectorStore
from tests.test_indexing_service import (
    make_deterministic_mock_encoder,
    seed_synthetic_chunks,
)


@pytest.fixture
def search_setup(tmp_path: Path):
    """Fixture providing an indexed database and SemanticSearchService."""
    db = Database(db_path=":memory:")
    doc_storage = DocumentStorage(db=db)
    seed_synthetic_chunks(doc_storage)

    mock_encoder = make_deterministic_mock_encoder(dim=384)
    emb_service = EmbeddingService(
        model_name="search-test-model",
        dimension=384,
        encoder_fn=mock_encoder,
    )
    vector_store = NumpyVectorStore(dimension=384, index_dir=tmp_path)

    indexing_service = IndexingService(
        document_storage=doc_storage,
        embedding_service=emb_service,
        vector_store=vector_store,
    )
    indexing_service.index_company_chunks(ticker="AAPL")

    search_service = SemanticSearchService(
        document_storage=doc_storage,
        embedding_service=emb_service,
        vector_store=vector_store,
    )
    return search_service


def test_semantic_search_ranking(search_setup: SemanticSearchService) -> None:
    """Verify semantic search ranks supply chain risk highest for risk query."""
    # Query contains 'supply' and 'risk'
    results = search_setup.search(
        query="What are the main supply chain risks?",
        top_k=2,
    )

    assert len(results) == 2
    top = results[0]
    assert top.section_identifier == "ITEM_1A"
    assert top.ticker == "AAPL"
    assert top.company_name == "Apple Inc."
    assert top.cik == "0000320193"
    assert top.filing_type == "10-K"
    assert top.accession_number == "0000320193-23-000106"
    assert "https://www.sec.gov" in top.source_url
    assert top.similarity_score > 0.9

    # Query contains 'sales'
    sales_results = search_setup.search(
        query="What were the total annual sales?",
        top_k=2,
    )
    assert len(sales_results) == 2
    assert sales_results[0].section_identifier == "ITEM_7"


def test_semantic_search_metadata_filtering(
    search_setup: SemanticSearchService,
) -> None:
    """Verify metadata filters for section, ticker, and filing type."""
    # Filter by section ITEM_7
    mda_results = search_setup.search(
        query="supply chain and sales risks",
        section_identifier="ITEM_7",
        top_k=5,
    )
    assert len(mda_results) == 1
    assert mda_results[0].section_identifier == "ITEM_7"

    # Filter by non-existent ticker
    msft_results = search_setup.search(
        query="supply chain",
        ticker="MSFT",
    )
    assert len(msft_results) == 0

    # Filter by filing type 10-Q (only 10-K is indexed)
    q_results = search_setup.search(
        query="supply chain",
        filing_type="10-Q",
    )
    assert len(q_results) == 0


def test_semantic_search_threshold_and_top_k(
    search_setup: SemanticSearchService,
) -> None:
    """Verify top_k limiting and similarity_threshold filtering."""
    # top_k = 1
    top1 = search_setup.search(query="risks", top_k=1)
    assert len(top1) == 1

    # High threshold filters out weaker matches
    high_thresh = search_setup.search(query="risks", similarity_threshold=0.999)
    assert len(high_thresh) <= 1


def test_semantic_search_empty_query(search_setup: SemanticSearchService) -> None:
    """Verify empty query raises ValueError."""
    with pytest.raises(ValueError, match="empty or whitespace-only"):
        search_setup.search(query="")

    with pytest.raises(ValueError, match="empty or whitespace-only"):
        search_setup.search(query="   \t\n")


def test_semantic_search_empty_index(tmp_path: Path) -> None:
    """Verify search returns empty list when index has no vectors."""
    db = Database(db_path=":memory:")
    doc_storage = DocumentStorage(db=db)
    emb_service = EmbeddingService(
        model_name="test-model",
        dimension=384,
        encoder_fn=make_deterministic_mock_encoder(384),
    )
    vector_store = NumpyVectorStore(dimension=384, index_dir=tmp_path)

    service = SemanticSearchService(
        document_storage=doc_storage,
        embedding_service=emb_service,
        vector_store=vector_store,
    )

    results = service.search(query="any query")
    assert results == []
