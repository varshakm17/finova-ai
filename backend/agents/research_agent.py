"""Research Agent for Finova AI Multi-Agent Orchestration.

Specialized in hybrid SEC filing retrieval (BM25 lexical + FAISS semantic)
and optional cross-encoder reranking, extracting high-relevance evidence passages.
"""

from __future__ import annotations

from typing import Any

from backend.agents.base_agent import BaseFinovaAgent
from backend.agents.state import FinovaAgentState
from backend.retrieval.hybrid_search import HybridSearchService
from backend.retrieval.reranker import CrossEncoderReranker
from backend.utils.logger import get_logger
from config.settings import Settings, get_settings

logger = get_logger("research_agent")


class ResearchAgent(BaseFinovaAgent):
    """Research Agent performing hybrid retrieval over ingested SEC filings."""

    def __init__(
        self,
        hybrid_search_service: HybridSearchService | None = None,
        reranker: CrossEncoderReranker | None = None,
        settings: Settings | None = None,
    ) -> None:
        super().__init__(
            agent_name="ResearchAgent",
            description="Performs dense semantic and sparse BM25 retrieval over SEC filings with provenance.",
        )
        self.settings = settings or get_settings()
        self.search_service = hybrid_search_service or HybridSearchService(
            settings=self.settings
        )
        self.reranker = reranker or CrossEncoderReranker(settings=self.settings)

    def execute(self, state: FinovaAgentState) -> dict[str, Any]:
        """Execute hybrid search and reranking on the user question or research query."""
        query = state.get("research_query") or state.get("user_question", "")
        ticker = state.get("company_ticker")
        top_k = state.get("metadata", {}).get("top_k_evidence", 5)

        logger.info(
            "ResearchAgent querying: '%s' (ticker=%s, top_k=%d)", query, ticker, top_k
        )
        evidence_list: list[dict[str, Any]] = []
        warnings: list[str] = []

        try:
            # Perform hybrid retrieval
            search_response = self.search_service.search(
                query=query,
                ticker=ticker,
                top_k=top_k * 2,  # pool for reranker
            )
            raw_candidates = search_response.results
            warnings.extend(search_response.warnings)

            if raw_candidates:
                # Apply cross-encoder reranker
                reranked_results, rerank_meta = self.reranker.rerank(
                    query=query,
                    candidates=raw_candidates,
                    top_k=top_k,
                )

                for item in reranked_results:
                    text_val = getattr(item, "chunk_text", getattr(item, "text", ""))
                    evidence_list.append(
                        {
                            "chunk_id": item.chunk_id,
                            "text": text_val,
                            "section_identifier": item.section_identifier,
                            "accession_number": item.accession_number,
                            "filing_date": item.filing_date,
                            "company_name": item.company_name,
                            "ticker": item.ticker,
                            "cik": item.cik,
                            "rerank_score": getattr(item, "rerank_score", None),
                            "hybrid_rank": getattr(item, "original_rank", None),
                        }
                    )
            else:
                warnings.append("No filing chunks found matching research query.")

        except Exception as exc:  # noqa: BLE001
            logger.error("ResearchAgent failed during retrieval: %s", exc)
            warnings.append(f"Research retrieval encountered an error: {exc}")

        return {
            "retrieved_evidence": evidence_list,
            "current_step": "research_agent",
            "warnings": warnings,
        }
