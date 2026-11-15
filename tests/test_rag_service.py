"""Unit and integration tests for RAGService orchestration and SQLite answer persistence."""

from unittest.mock import MagicMock

from backend.data.storage import Database
from backend.llm.llm_provider import MockLLMProvider
from backend.rag.citation_validator import CitationValidator
from backend.rag.context_builder import BuiltContext, RAGContextBuilder
from backend.rag.rag_models import (
    CalculationEvidence,
    RAGAnswer,
    RAGRequest,
    RetrievedEvidence,
)
from backend.rag.rag_service import RAGService


def create_sample_context() -> BuiltContext:
    retrieved = [
        RetrievedEvidence(
            evidence_id="E1",
            chunk_id="chk_001",
            ticker="AAPL",
            company_name="Apple Inc.",
            filing_type="10-K",
            filing_date="2023-11-03",
            accession_number="0000320193-23-000106",
            section_identifier="ITEM_1A",
            section_title="Risk Factors",
            chunk_text="Global economic conditions and international trade restrictions present key operational risks.",
            source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
        )
    ]
    calculations = [
        CalculationEvidence(
            evidence_id="C1",
            calculation_id="calc_om_01",
            metric_name="operating_margin",
            calculated_value=30.13,
            unit="percentage",
            formula="OperatingIncome / TotalRevenue",
            period_end="2023-09-30",
        )
    ]
    return BuiltContext(
        prompt_context_text="[E1] Risk factors...\n[C1] Operating margin: 30.13%",
        retrieved_evidence=retrieved,
        calculation_evidence=calculations,
        retrieval_method="hybrid_reranked",
        warnings=[],
        has_sufficient_evidence=True,
    )


def test_rag_service_successful_answer() -> None:
    db = Database(db_path=":memory:")
    mock_context_builder = MagicMock(spec=RAGContextBuilder)
    mock_context_builder.build_context.return_value = create_sample_context()

    mock_llm = MockLLMProvider(
        default_response="Apple faces global economic risks [E1]. Its operating margin stood at 30.13% in FY2023 [C1]."
    )

    service = RAGService(
        llm_provider=mock_llm,
        context_builder=mock_context_builder,
        citation_validator=CitationValidator(),
        database=db,
    )

    req = RAGRequest(
        question="What are Apple's risks and operating margin?", ticker="AAPL"
    )
    answer = service.ask(req)

    assert isinstance(answer, RAGAnswer)
    assert answer.answer_status == "answered"
    assert "Apple faces global economic risks" in answer.answer
    assert len(answer.citations) == 2
    assert answer.citations[0].citation_id == "E1"
    assert answer.citations[1].citation_id == "C1"
    assert answer.provider == "mock"
    assert answer.retrieval_method == "hybrid_reranked"

    # Verify persistent retrieval from SQLite
    saved_answer = service.get_answer(answer.answer_id)
    assert saved_answer is not None
    assert saved_answer.answer_id == answer.answer_id
    assert saved_answer.answer == answer.answer
    assert len(saved_answer.citations) == 2


def test_rag_service_insufficient_evidence() -> None:
    db = Database(db_path=":memory:")
    mock_context_builder = MagicMock(spec=RAGContextBuilder)
    # Context with 0 evidence
    mock_context_builder.build_context.return_value = BuiltContext(
        prompt_context_text="",
        retrieved_evidence=[],
        calculation_evidence=[],
        retrieval_method="hybrid",
        warnings=["No matching chunks found."],
        has_sufficient_evidence=False,
    )

    mock_llm = MagicMock(spec=MockLLMProvider)
    service = RAGService(
        llm_provider=mock_llm,
        context_builder=mock_context_builder,
        database=db,
    )

    req = RAGRequest(question="What were the Q3 profits of UnknownCorp?", ticker="XYZ")
    answer = service.ask(req)

    assert answer.answer_status == "insufficient_evidence"
    assert "do not provide sufficient verified evidence" in answer.answer
    # Ensure LLM generate was NEVER called when evidence is insufficient
    mock_llm.generate.assert_not_called()


def test_rag_service_provider_offline() -> None:
    db = Database(db_path=":memory:")
    mock_context_builder = MagicMock(spec=RAGContextBuilder)
    mock_context_builder.build_context.return_value = create_sample_context()

    # Provider health check returns False
    mock_llm = MockLLMProvider(healthy=False)

    service = RAGService(
        llm_provider=mock_llm,
        context_builder=mock_context_builder,
        database=db,
    )

    req = RAGRequest(question="What are Apple risks?", ticker="AAPL")
    answer = service.ask(req)

    assert answer.answer_status == "provider_unavailable"
    assert "currently unreachable or offline" in answer.answer
    assert len(answer.retrieved_evidence) == 1


def test_rag_service_generation_exception() -> None:
    db = Database(db_path=":memory:")
    mock_context_builder = MagicMock(spec=RAGContextBuilder)
    mock_context_builder.build_context.return_value = create_sample_context()

    mock_llm = MagicMock(spec=MockLLMProvider)
    mock_llm.health_check.return_value = True
    mock_llm.model_name = "mock-model"
    mock_llm.provider_name = "mock"
    mock_llm.generate.side_effect = RuntimeError("GPU out of memory")

    service = RAGService(
        llm_provider=mock_llm,
        context_builder=mock_context_builder,
        database=db,
    )

    req = RAGRequest(question="Explain risk factors", ticker="AAPL")
    answer = service.ask(req)

    assert answer.answer_status == "generation_failed"
    assert "GPU out of memory" in answer.answer


def test_rag_service_citation_validation_unsupported() -> None:
    db = Database(db_path=":memory:")
    mock_context_builder = MagicMock(spec=RAGContextBuilder)
    mock_context_builder.build_context.return_value = create_sample_context()

    # Model references non-existent [E99]
    mock_llm = MockLLMProvider(
        default_response="Apple has risks [E1] and unverified lawsuits [E99]."
    )

    service = RAGService(
        llm_provider=mock_llm,
        context_builder=mock_context_builder,
        citation_validator=CitationValidator(),
        database=db,
    )

    req = RAGRequest(question="Explain risk factors", ticker="AAPL")
    answer = service.ask(req)

    assert answer.answer_status in ("partially_supported", "verification_rejected")
    assert any("unsupported citation identifier(s): E99" in w for w in answer.warnings)


def test_rag_service_get_capabilities() -> None:
    db = Database(db_path=":memory:")
    mock_llm = MockLLMProvider()

    service = RAGService(
        llm_provider=mock_llm,
        database=db,
    )

    caps = service.get_capabilities()
    assert "hybrid_reranked" in caps.supported_retrieval_modes
    assert caps.reranker_available is True
    assert caps.calculation_engine_enabled is True
    assert caps.citation_verification_enabled is True
    assert caps.llm_provider == "mock"
    assert caps.llm_online is True
