"""RAG Agent for Finova AI Multi-Agent Orchestration.

Synthesizes evidence-grounded financial research responses using retrieved SEC filing
passages and deterministic calculation receipts with strict citation attribution.
"""

from __future__ import annotations

from typing import Any

from backend.agents.base_agent import BaseFinovaAgent
from backend.agents.state import FinovaAgentState
from backend.llm import get_llm_provider
from backend.llm.llm_provider import LLMProvider
from backend.rag.citation_validator import CitationValidator
from backend.rag.prompt_templates import build_rag_prompts
from backend.utils.logger import get_logger
from config.settings import Settings, get_settings

logger = get_logger("rag_agent")


class RAGAgent(BaseFinovaAgent):
    """RAG Answer Agent that generates grounded synthesis from evidence and calculation receipts."""

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        citation_validator: CitationValidator | None = None,
        settings: Settings | None = None,
    ) -> None:
        super().__init__(
            agent_name="RAGAgent",
            description="Generates grounded answers from verified SEC filing excerpts and calculation receipts.",
        )
        self.settings = settings or get_settings()
        self.llm = llm_provider or get_llm_provider(settings=self.settings)
        self.citation_validator = citation_validator or CitationValidator()

    def build_context_text(
        self,
        retrieved_evidence: list[dict[str, Any]],
        calculation_results: list[dict[str, Any]],
    ) -> str:
        """Format calculation receipts and retrieved filing chunks into structured context."""
        context_blocks: list[str] = []

        if calculation_results:
            context_blocks.append(
                "--- VERIFIED FINANCIAL CALCULATIONS (DETERMINISTIC PYTHON RECEIPTS) ---"
            )
            for idx, r in enumerate(calculation_results, start=1):
                cid = f"C{idx}"
                metric = r.get("metric_name") or r.get(
                    "metric_display_name", "Unknown Metric"
                )
                val = r.get("calculated_value")
                unit = r.get("unit", "")
                val_str = (
                    f"{val:.2f}%"
                    if unit == "percentage" and isinstance(val, (int, float))
                    else f"{val} {unit}"
                )
                formula = r.get("formula_definition") or r.get("formula", "N/A")
                period = f"{r.get('fiscal_year', 'N/A')} {r.get('fiscal_period', '')}".strip()
                block = (
                    f"[{cid}] METRIC: {metric}\n"
                    f"  Value: {val_str}\n"
                    f"  Formula: {formula}\n"
                    f"  Period: {period}\n"
                    f"  Filing Provenance: {r.get('calculation_id', 'N/A')}"
                )
                context_blocks.append(block)

        if retrieved_evidence:
            context_blocks.append("--- VERIFIED SEC FILING DISCLOSURES ---")
            for idx, ev in enumerate(retrieved_evidence, start=1):
                eid = f"E{idx}"
                company = ev.get("company_name", "Target Company")
                ticker = ev.get("ticker", "")
                section = ev.get("section_identifier", "Disclosures")
                text = ev.get("text", "")
                accession = ev.get("accession_number", "N/A")
                date = ev.get("filing_date", "N/A")
                block = (
                    f"[{eid}] COMPANY: {company} ({ticker})\n"
                    f"  Filing Date: {date} | Accession: {accession}\n"
                    f"  Section: {section}\n"
                    f"  Text: {text}"
                )
                context_blocks.append(block)

        return "\n\n".join(context_blocks)

    def execute(self, state: FinovaAgentState) -> dict[str, Any]:
        """Generate evidence-grounded answer citing retrieved evidence and receipts."""
        question = state.get("user_question", "")
        retrieved_evidence = state.get("retrieved_evidence", [])
        calculation_results = state.get("calculation_results", [])
        mock_response = state.get("mock_llm_response")

        warnings: list[str] = []

        # If a mock response is explicitly supplied, use it
        if mock_response:
            logger.info("RAGAgent: Using mock LLM response provided in state.")
            return {
                "generated_answer": mock_response,
                "current_step": "rag_agent",
            }

        # Check for complete lack of evidence
        if not retrieved_evidence and not calculation_results:
            msg = "The available SEC filing disclosures and financial calculations do not provide sufficient evidence to answer this question."
            return {
                "generated_answer": msg,
                "current_step": "rag_agent",
                "warnings": ["Insufficient evidence available for RAG generation."],
            }

        context_text = self.build_context_text(retrieved_evidence, calculation_results)
        system_prompt, user_prompt = build_rag_prompts(
            question=question,
            context_text=context_text,
            response_style="detailed",
        )

        try:
            llm_res = self.llm.generate(
                prompt=user_prompt,
                system=system_prompt,
                temperature=0.0,
            )
            answer_text = llm_res.text
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "RAGAgent LLM generation failed or unavailable (%s). Constructing fallback grounded answer.",
                exc,
            )
            warnings.append(
                f"LLM generation failed: {exc}. Using deterministic evidence summary."
            )
            # Fallback deterministic answer from retrieved items
            summary_parts = []
            if calculation_results:
                summary_parts.append("Calculated Metrics:")
                for idx, r in enumerate(calculation_results[:3], start=1):
                    val = r.get("calculated_value")
                    name = r.get("metric_name", "Metric")
                    summary_parts.append(f"- {name}: {val} [C{idx}]")
            if retrieved_evidence:
                summary_parts.append("Filing Disclosures:")
                for idx, ev in enumerate(retrieved_evidence[:2], start=1):
                    snip = ev.get("text", "")[:180].strip()
                    summary_parts.append(f'- "{snip}..." [E{idx}]')
            answer_text = (
                "\n".join(summary_parts) if summary_parts else "No evidence available."
            )

        return {
            "generated_answer": answer_text,
            "current_step": "rag_agent",
            "warnings": warnings,
        }
