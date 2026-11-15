"""Unit tests for Cross-Encoder Reranker service.

Verifies lazy initialization, candidate re-ranking, provenance preservation,
batch processing, disabled mode, fallback resilience, and CPU execution.
Zero network access; uses injected mock models.
"""

from unittest.mock import MagicMock

from backend.retrieval.reranker import CrossEncoderReranker
from backend.retrieval.retrieval_models import HybridSearchResult
from config.settings import Settings


def _create_sample_hybrid_candidate(
    chunk_id: str, text: str, rrf: float, rank: int
) -> HybridSearchResult:
    """Helper to construct dummy HybridSearchResult."""
    return HybridSearchResult(
        chunk_id=chunk_id,
        ticker="AAPL",
        company_name="Apple Inc.",
        cik="0000320193",
        filing_type="10-K",
        filing_date="2023-11-03",
        report_date="2023-09-30",
        accession_number="0000320193-23-000106",
        section_identifier="ITEM_1A",
        section_title="Risk Factors",
        chunk_text=text,
        source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
        dense_rank=rank,
        dense_score=0.75,
        sparse_rank=rank,
        bm25_score=15.2,
        rrf_score=rrf,
        retrieval_sources=["dense", "sparse"],
    )


def test_lazy_initialization() -> None:
    """Verify reranker does not load model weights on instantiation."""
    reranker = CrossEncoderReranker()
    assert not reranker.is_initialized
    assert reranker.is_available
    assert reranker._model is None


def test_reranker_reordering_with_mock_model() -> None:
    """Verify that cross-encoder scores re-order candidates descending by score."""
    mock_model = MagicMock()
    # Candidate 2 receives score 3.5, candidate 1 receives 1.2
    mock_model.predict.return_value = [1.2, 3.5]

    cand1 = _create_sample_hybrid_candidate("chunk_1", "Supply chain risks", 0.03, 1)
    cand2 = _create_sample_hybrid_candidate(
        "chunk_2", "Severe component shortage", 0.02, 2
    )

    reranker = CrossEncoderReranker(model=mock_model)
    results, meta = reranker.rerank(
        query="Component shortages",
        candidates=[cand1, cand2],
        top_k=2,
    )

    assert meta["reranker_applied"] is True
    assert meta["status"] == "success"
    assert len(results) == 2

    # cand2 had higher score (3.5), so it should be rank 1
    assert results[0].chunk_id == "chunk_2"
    assert results[0].rerank_rank == 1
    assert results[0].rerank_score == 3.5
    assert results[0].original_rank == 2

    # cand1 had lower score (1.2), so it should be rank 2
    assert results[1].chunk_id == "chunk_1"
    assert results[1].rerank_rank == 2
    assert results[1].rerank_score == 1.2
    assert results[1].original_rank == 1


def test_provenance_preservation() -> None:
    """Verify all statutory filing metadata and original scores are preserved."""
    mock_model = MagicMock()
    mock_model.predict.return_value = [2.0]

    cand = _create_sample_hybrid_candidate("chunk_aapl_1", "Text content", 0.05, 1)
    reranker = CrossEncoderReranker(model=mock_model)

    results, _ = reranker.rerank("Query", [cand], top_k=1)
    res = results[0]

    assert res.chunk_id == "chunk_aapl_1"
    assert res.ticker == "AAPL"
    assert res.company_name == "Apple Inc."
    assert res.cik == "0000320193"
    assert res.filing_type == "10-K"
    assert res.accession_number == "0000320193-23-000106"
    assert res.section_identifier == "ITEM_1A"
    assert res.source_url.startswith("https://www.sec.gov/")
    assert res.original_dense_rank == 1
    assert res.original_sparse_rank == 1
    assert res.original_rrf_score == 0.05
    assert res.retrieval_sources == ["dense", "sparse"]


def test_batch_size_configuration() -> None:
    """Verify predict receives the configured batch size."""
    mock_model = MagicMock()
    mock_model.predict.return_value = [1.0, 2.0]

    custom_settings = Settings(RERANKER_BATCH_SIZE=8)
    reranker = CrossEncoderReranker(settings=custom_settings, model=mock_model)

    cand1 = _create_sample_hybrid_candidate("c1", "Text 1", 0.01, 1)
    cand2 = _create_sample_hybrid_candidate("c2", "Text 2", 0.02, 2)

    reranker.rerank("Query", [cand1, cand2])
    mock_model.predict.assert_called_once()
    _, kwargs = mock_model.predict.call_args
    assert kwargs.get("batch_size") == 8


def test_disabled_mode() -> None:
    """Verify reranker returns candidates in original order when disabled by configuration."""
    disabled_settings = Settings(RERANKER_ENABLED=False)
    reranker = CrossEncoderReranker(settings=disabled_settings)

    cand1 = _create_sample_hybrid_candidate("c1", "Text 1", 0.05, 1)
    cand2 = _create_sample_hybrid_candidate("c2", "Text 2", 0.03, 2)

    results, meta = reranker.rerank("Query", [cand1, cand2], top_k=2)

    assert meta["reranker_applied"] is False
    assert meta["status"] == "disabled_by_config"
    assert len(results) == 2
    assert results[0].chunk_id == "c1"
    assert results[1].chunk_id == "c2"


def test_empty_candidates_handling() -> None:
    """Verify empty candidate list does not trigger errors."""
    reranker = CrossEncoderReranker()
    results, meta = reranker.rerank("Query", [])
    assert results == []
    assert meta["status"] == "empty_candidates"


def test_reranker_status_reporting() -> None:
    """Verify get_status returns valid RerankerStatusResponse."""
    custom_settings = Settings(
        RERANKER_ENABLED=True,
        RERANKER_MODEL_NAME="cross-encoder/ms-marco-MiniLM-L-6-v2",
        RERANKER_DEVICE="cpu",
    )
    reranker = CrossEncoderReranker(settings=custom_settings)
    status = reranker.get_status()

    assert status.enabled is True
    assert status.device == "cpu"
    assert status.model_name == "cross-encoder/ms-marco-MiniLM-L-6-v2"
    assert status.initialized is False


def test_latency_benchmark_with_mock() -> None:
    """Verify benchmark_latency evaluates pairs and returns metrics."""
    mock_model = MagicMock()
    mock_model.predict.return_value = [0.5, 0.6]

    reranker = CrossEncoderReranker(model=mock_model)
    res = reranker.benchmark_latency(sample_chunks=["text a", "text b"])

    assert res["benchmarked"] is True
    assert res["pairs_evaluated"] == 2
    assert "total_latency_ms" in res


def test_reranker_with_dict_candidates() -> None:
    """Verify reranking operates cleanly on dictionary candidate inputs."""
    mock_model = MagicMock()
    mock_model.predict.return_value = [3.0, 1.0]

    dict_cand1 = {
        "chunk_id": "dc_1",
        "ticker": "AAPL",
        "company_name": "Apple",
        "cik": "0000320193",
        "filing_type": "10-K",
        "filing_date": "2023-11-03",
        "accession_number": "0000320193-23-000106",
        "section_identifier": "ITEM_1A",
        "section_title": "Risk",
        "chunk_text": "Supply disruption risk",
        "source_url": "https://www.sec.gov/doc.htm",
        "rrf_score": 0.02,
    }
    dict_cand2 = {
        "chunk_id": "dc_2",
        "ticker": "AAPL",
        "company_name": "Apple",
        "cik": "0000320193",
        "filing_type": "10-K",
        "filing_date": "2023-11-03",
        "accession_number": "0000320193-23-000106",
        "section_identifier": "ITEM_1A",
        "section_title": "Risk",
        "chunk_text": "Foreign currency exposure",
        "rrf_score": 0.01,
    }

    reranker = CrossEncoderReranker(model=mock_model)
    results, meta = reranker.rerank("Supply risks", [dict_cand1, dict_cand2])

    assert meta["reranker_applied"] is True
    assert len(results) == 2
    assert results[0].chunk_id == "dc_1"
    assert results[0].rerank_rank == 1

    # Test fallback with dict candidates
    fallback_res = reranker._fallback_results([dict_cand1, dict_cand2], top_k=2)
    assert len(fallback_res) == 2
    assert fallback_res[0].chunk_id == "dc_1"


def test_reranker_prediction_error_handling() -> None:
    """Verify prediction exceptions fall back gracefully without unhandled crashes."""
    mock_model = MagicMock()
    mock_model.predict.side_effect = RuntimeError("Prediction computation error")

    cand = _create_sample_hybrid_candidate("c1", "Text", 0.05, 1)
    reranker = CrossEncoderReranker(model=mock_model)

    results, meta = reranker.rerank("Query", [cand], top_k=1)
    assert meta["reranker_applied"] is False
    assert meta["status"] == "prediction_error"
    assert "Prediction computation error" in meta["error"]
    assert len(results) == 1
    assert results[0].chunk_id == "c1"


def test_reranker_model_load_failure() -> None:
    """Verify initialization failure falls back cleanly."""
    reranker = CrossEncoderReranker()
    # Force _load_model failure by patching import or exception
    reranker._load_model = lambda: None  # type: ignore[assignment]
    reranker._init_error = "Mocked weight download error"

    cand = _create_sample_hybrid_candidate("c1", "Text", 0.05, 1)
    results, meta = reranker.rerank("Query", [cand])

    assert meta["reranker_applied"] is False
    assert meta["status"] == "model_unavailable"
    assert results[0].chunk_id == "c1"


def test_latency_benchmark_error_branches() -> None:
    """Verify benchmark_latency error paths when disabled or model fails."""
    disabled_reranker = CrossEncoderReranker(settings=Settings(RERANKER_ENABLED=False))
    res_disabled = disabled_reranker.benchmark_latency()
    assert res_disabled["benchmarked"] is False
    assert "disabled" in res_disabled["error"].lower()

    fail_reranker = CrossEncoderReranker()
    fail_reranker._load_model = lambda: None  # type: ignore[assignment]
    fail_reranker._init_error = "Could not load"
    res_fail = fail_reranker.benchmark_latency()
    assert res_fail["benchmarked"] is False
    assert "could not be loaded" in res_fail["error"].lower()


def test_reranker_status_messages() -> None:
    """Verify status messages for disabled, initialized, and error states."""
    r_dis = CrossEncoderReranker(settings=Settings(RERANKER_ENABLED=False))
    assert "disabled" in r_dis.get_status().message.lower()

    r_init = CrossEncoderReranker(model=MagicMock())
    assert "loaded" in r_init.get_status().message.lower()

    r_err = CrossEncoderReranker()
    r_err._init_error = "Network failure"
    assert "failed" in r_err.get_status().message.lower()
