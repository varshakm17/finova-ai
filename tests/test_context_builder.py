"""Unit tests for RAG Context Builder, evidence ranking, and calculation receipt injection."""

from unittest.mock import MagicMock

from backend.data.document_storage import DocumentStorage
from backend.data.storage import Database
from backend.evaluation.evidence_validator import EvidenceQualityValidator
from backend.rag.context_builder import RAGContextBuilder
from backend.retrieval.hybrid_search import HybridSearchService
from backend.retrieval.reranker import CrossEncoderReranker
from backend.retrieval.retrieval_models import HybridSearchResult, RerankedSearchResult


def test_identify_relevant_metrics() -> None:
    builder = RAGContextBuilder(
        hybrid_search_service=MagicMock(),
        reranker=MagicMock(),
        validator=MagicMock(),
        database=MagicMock(),
        document_storage=MagicMock(),
    )

    metrics1 = builder.identify_relevant_metrics(
        "What was Apple's gross margin and operating margin?"
    )
    assert "gross_margin" in metrics1
    assert "operating_margin" in metrics1

    metrics2 = builder.identify_relevant_metrics(
        "Show me the free cash flow and current ratio."
    )
    assert "free_cash_flow" in metrics2
    assert "current_ratio" in metrics2

    metrics3 = builder.identify_relevant_metrics("What are the company's risk factors?")
    assert len(metrics3) == 0


def test_fetch_calculation_evidence() -> None:
    mock_db = MagicMock()
    mock_db.get_financial_calculations.return_value = [
        {
            "calculation_id": "calc_gm_2023",
            "metric_name": "gross_margin",
            "calculated_value": 44.13,
            "unit": "percentage",
            "formula_expression": "GrossProfit / TotalRevenue",
            "period_end": "2023-09-30",
            "inputs": [{"tag": "GrossProfit", "value": 169148000000}],
            "status": "calculated",
        }
    ]

    builder = RAGContextBuilder(
        hybrid_search_service=MagicMock(),
        reranker=MagicMock(),
        validator=MagicMock(),
        database=mock_db,
        document_storage=MagicMock(),
    )

    calcs = builder.fetch_calculation_evidence(
        ticker="AAPL", question="What was the gross margin?"
    )
    assert len(calcs) == 1
    assert calcs[0].evidence_id == "C1"
    assert calcs[0].metric_name == "gross_margin"
    assert calcs[0].calculated_value == 44.13
    assert calcs[0].formula == "GrossProfit / TotalRevenue"


def test_build_context_with_hybrid_and_calculations() -> None:
    mock_hybrid = MagicMock(spec=HybridSearchService)
    mock_reranker = MagicMock(spec=CrossEncoderReranker)
    mock_validator = MagicMock(spec=EvidenceQualityValidator)
    mock_db = MagicMock(spec=Database)
    mock_doc_storage = MagicMock(spec=DocumentStorage)

    # Setup hybrid results
    sample_hybrid = HybridSearchResult(
        chunk_id="chk_1",
        ticker="AAPL",
        company_name="Apple Inc.",
        cik="0000320193",
        filing_type="10-K",
        filing_date="2023-11-03",
        report_date="2023-09-30",
        accession_number="0000320193-23-000106",
        section_identifier="ITEM_1A",
        section_title="Risk Factors",
        chunk_text="Global economic volatility and supply chain concentration represent principal risks.",
        source_url="https://www.sec.gov/edgar/data/320193/000032019323000106/aapl-20230930.htm",
        retrieval_sources=["dense", "bm25"],
        rrf_score=0.033,
        dense_score=0.88,
        bm25_score=12.5,
        dense_rank=1,
        bm25_rank=1,
    )
    mock_hybrid.search.return_value = [sample_hybrid]

    # Setup reranker results
    sample_reranked = RerankedSearchResult(
        chunk_id="chk_1",
        ticker="AAPL",
        company_name="Apple Inc.",
        cik="0000320193",
        filing_type="10-K",
        filing_date="2023-11-03",
        report_date="2023-09-30",
        accession_number="0000320193-23-000106",
        section_identifier="ITEM_1A",
        section_title="Risk Factors",
        chunk_text="Global economic volatility and supply chain concentration represent principal risks.",
        source_url="https://www.sec.gov/edgar/data/320193/000032019323000106/aapl-20230930.htm",
        original_rank=1,
        rerank_rank=1,
        rerank_score=0.95,
        original_dense_score=0.88,
        original_bm25_score=12.5,
        rrf_score=0.033,
    )
    mock_reranker.is_available = True
    mock_reranker.rerank.return_value = ([sample_reranked], {"reranker_applied": True})

    # Setup validator result
    val_report = MagicMock()
    val_report.chunk_validations = []
    mock_validator.validate_chunks.return_value = val_report

    # Setup calculations
    mock_db.get_financial_calculations.return_value = [
        {
            "calculation_id": "calc_om_2023",
            "metric_name": "operating_margin",
            "calculated_value": 30.13,
            "unit": "percentage",
            "formula_expression": "OperatingIncome / TotalRevenue",
            "period_end": "2023-09-30",
            "inputs": [],
            "status": "calculated",
        }
    ]

    builder = RAGContextBuilder(
        hybrid_search_service=mock_hybrid,
        reranker=mock_reranker,
        validator=mock_validator,
        database=mock_db,
        document_storage=mock_doc_storage,
    )

    built = builder.build_context(
        question="What are the key risk factors and operating margin?",
        ticker="AAPL",
        top_k=3,
        use_reranker=True,
        include_calculations=True,
    )

    assert built.has_sufficient_evidence is True
    assert built.retrieval_method == "hybrid_reranked"
    assert len(built.retrieved_evidence) == 1
    assert built.retrieved_evidence[0].evidence_id == "E1"
    assert "Global economic volatility" in built.retrieved_evidence[0].chunk_text

    assert len(built.calculation_evidence) == 1
    assert built.calculation_evidence[0].evidence_id == "C1"
    assert built.calculation_evidence[0].calculated_value == 30.13

    # Check prompt context text formatting
    assert "[E1] COMPANY: Apple Inc." in built.prompt_context_text
    assert "[C1] METRIC: operating_margin" in built.prompt_context_text


def test_build_context_no_results() -> None:
    mock_hybrid = MagicMock(spec=HybridSearchService)
    mock_hybrid.search.return_value = []

    builder = RAGContextBuilder(
        hybrid_search_service=mock_hybrid,
        reranker=MagicMock(),
        validator=MagicMock(),
        database=MagicMock(),
        document_storage=MagicMock(),
    )

    built = builder.build_context(question="Nonexistent company question", ticker="XYZ")
    assert len(built.retrieved_evidence) == 0
    assert built.has_sufficient_evidence is False
    assert any("No filing passages retrieved" in w for w in built.warnings)


def test_build_context_provenance_filtering_and_temporal_warning() -> None:
    mock_hybrid = MagicMock(spec=HybridSearchService)
    mock_validator = MagicMock(spec=EvidenceQualityValidator)
    mock_db = MagicMock(spec=Database)
    mock_doc_storage = MagicMock(spec=DocumentStorage)

    c1 = HybridSearchResult(
        chunk_id="chk_good",
        ticker="AAPL",
        company_name="Apple Inc.",
        cik="0000320193",
        filing_type="10-K",
        filing_date="2023-11-03",
        report_date="2023-09-30",
        accession_number="0000320193-23-000106",
        section_identifier="ITEM_1A",
        section_title="Risk Factors",
        chunk_text="Operational supply chain risks.",
        source_url="https://www.sec.gov",
        retrieval_sources=["dense"],
        rrf_score=0.03,
        dense_score=0.85,
    )
    c2 = HybridSearchResult(
        chunk_id="chk_bad",
        ticker="AAPL",
        company_name="Apple Inc.",
        cik="0000320193",
        filing_type="10-K",
        filing_date="2022-10-28",
        report_date="2022-09-24",
        accession_number="0000320193-22-000108",
        section_identifier="ITEM_7",
        section_title="MD&A",
        chunk_text="Older disclosures.",
        source_url="https://www.sec.gov",
        retrieval_sources=["bm25"],
        rrf_score=0.02,
        dense_score=0.75,
    )
    mock_hybrid.search.return_value = [c1, c2]

    # Setup validator output: c1 has temporal_mismatch, c2 has incomplete_provenance
    val_report = MagicMock()
    v1 = MagicMock()
    v1.status = "temporal_mismatch"
    v1.reporting_period = "2023-09-30"

    v2 = MagicMock()
    v2.status = "incomplete_provenance"
    v2.reporting_period = "2022-09-24"

    val_report.chunk_validations = [v1, v2]
    mock_validator.validate_chunks.return_value = val_report

    mock_db.get_financial_calculations.return_value = []

    builder = RAGContextBuilder(
        hybrid_search_service=mock_hybrid,
        reranker=MagicMock(is_available=False),
        validator=mock_validator,
        database=mock_db,
        document_storage=mock_doc_storage,
    )

    built = builder.build_context(
        question="What are risk factors?",
        ticker="AAPL",
        use_reranker=False,
        include_calculations=False,
    )

    # c2 excluded due to incomplete_provenance, c1 retained with warning
    assert len(built.retrieved_evidence) == 1
    assert built.retrieved_evidence[0].chunk_id == "chk_good"
    assert any("incomplete_provenance" in w for w in built.warnings)
    assert any("temporal_mismatch" in w or "multi-period" in w for w in built.warnings)


def test_build_context_accession_filter() -> None:
    mock_hybrid = MagicMock(spec=HybridSearchService)
    c1 = HybridSearchResult(
        chunk_id="chk_1",
        ticker="AAPL",
        company_name="Apple Inc.",
        cik="0000320193",
        filing_type="10-K",
        filing_date="2023-11-03",
        report_date="2023-09-30",
        accession_number="0000320193-23-000106",
        section_identifier="ITEM_1A",
        section_title="Risk Factors",
        chunk_text="2023 risks.",
        source_url="https://www.sec.gov",
        retrieval_sources=["dense"],
        rrf_score=0.03,
    )
    c2 = HybridSearchResult(
        chunk_id="chk_2",
        ticker="AAPL",
        company_name="Apple Inc.",
        cik="0000320193",
        filing_type="10-K",
        filing_date="2022-10-28",
        report_date="2022-09-24",
        accession_number="0000320193-22-000108",
        section_identifier="ITEM_1A",
        section_title="Risk Factors",
        chunk_text="2022 risks.",
        source_url="https://www.sec.gov",
        retrieval_sources=["dense"],
        rrf_score=0.02,
    )
    mock_hybrid.search.return_value = [c1, c2]

    val_report = MagicMock()
    val_report.chunk_validations = []

    builder = RAGContextBuilder(
        hybrid_search_service=mock_hybrid,
        reranker=MagicMock(is_available=False),
        validator=MagicMock(validate_chunks=MagicMock(return_value=val_report)),
        database=MagicMock(get_financial_calculations=MagicMock(return_value=[])),
        document_storage=MagicMock(),
    )

    built = builder.build_context(
        question="Risks?",
        ticker="AAPL",
        accession_number="0000320193-23-000106",
        use_reranker=False,
    )
    assert len(built.retrieved_evidence) == 1
    assert built.retrieved_evidence[0].accession_number == "0000320193-23-000106"
