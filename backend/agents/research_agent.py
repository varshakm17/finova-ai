"""Research Agent for Finova AI Multi-Agent Orchestration.

Specialized in hybrid SEC filing retrieval (BM25 lexical + FAISS semantic),
cross-encoder reranking, multi-task plan execution, and evidence deduplication.
"""

from __future__ import annotations

from typing import Any

from backend.agents.agent_models import ResearchTaskResult, TaskStatus, TaskType
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
        search_service: HybridSearchService | None = None,
        cross_encoder: CrossEncoderReranker | None = None,
    ) -> None:
        super().__init__(
            agent_name="ResearchAgent",
            description="Performs dense semantic and sparse BM25 retrieval over SEC filings with provenance.",
        )
        self.settings = settings or get_settings()
        self.search_service = (
            hybrid_search_service
            or search_service
            or HybridSearchService(settings=self.settings)
        )
        self.reranker = (
            reranker or cross_encoder or CrossEncoderReranker(settings=self.settings)
        )

    def _execute_single_query(
        self,
        query: str,
        ticker: str | None,
        section_identifier: str | None = None,
        top_k: int = 5,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Run hybrid search and reranking for a specific query and section filter."""
        evidence_list: list[dict[str, Any]] = []
        warnings: list[str] = []

        try:
            search_response = self.search_service.search(
                query=query,
                ticker=ticker,
                section_identifier=section_identifier,
                top_k=top_k * 2,
            )
            raw_candidates = search_response.results
            warnings.extend(search_response.warnings)

            if raw_candidates:
                reranked_results, _ = self.reranker.rerank(
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
                            "section_title": getattr(item, "section_title", "Disclosures"),
                            "accession_number": item.accession_number,
                            "filing_type": getattr(item, "filing_type", "10-K"),
                            "filing_date": item.filing_date,
                            "report_date": getattr(item, "report_date", None),
                            "company_name": item.company_name,
                            "ticker": item.ticker,
                            "cik": item.cik,
                            "source_url": getattr(item, "source_url", "https://www.sec.gov"),
                            "rerank_score": getattr(item, "rerank_score", None),
                            "hybrid_rank": getattr(item, "original_rank", None),
                        }
                    )
            else:
                warnings.append(f"No filing chunks found for query '{query[:50]}'.")

        except Exception as exc:  # noqa: BLE001
            logger.error("Research retrieval query failed: %s", exc)
            warnings.append(f"Retrieval error: {exc}")

        return evidence_list, warnings

    def execute_plan(
        self,
        plan_dict: dict[str, Any],
        ticker: str | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        """Execute all retrieval tasks outlined in a structured research plan."""
        tasks = plan_dict.get("tasks", [])
        all_evidence_by_id: dict[str, dict[str, Any]] = {}
        task_results: list[dict[str, Any]] = []
        global_warnings: list[str] = []

        # Filter tasks relevant for retrieval
        retrieval_types = {
            TaskType.FILING_RETRIEVAL.value,
            TaskType.MDA_ANALYSIS.value,
            TaskType.RISK_ANALYSIS.value,
        }

        evidence_counter = 1

        for task in tasks:
            t_type = task.get("task_type")
            t_id = task.get("task_id", "task_unknown")
            t_title = task.get("title", "")
            t_desc = task.get("description", "")
            target_sections = task.get("target_sections") or []

            # If task is not retrieval-focused, skip or mark pending
            if t_type not in retrieval_types and not target_sections:
                continue

            query_text = f"{t_title}. {t_desc}"
            task_evidence: list[dict[str, Any]] = []
            task_warnings: list[str] = []

            if target_sections:
                for sec in target_sections:
                    sec_ev, sec_warn = self._execute_single_query(
                        query=query_text,
                        ticker=ticker,
                        section_identifier=sec,
                        top_k=3,
                    )
                    task_evidence.extend(sec_ev)
                    task_warnings.extend(sec_warn)
            else:
                gen_ev, gen_warn = self._execute_single_query(
                    query=query_text,
                    ticker=ticker,
                    top_k=4,
                )
                task_evidence.extend(gen_ev)
                task_warnings.extend(gen_warn)

            # Deduplicate chunks within task and assign evidence_ids
            task_ev_ids: list[str] = []
            filing_refs: set[str] = set()

            for ev in task_evidence:
                cid = ev["chunk_id"]
                if cid not in all_evidence_by_id:
                    ev["evidence_id"] = f"E{evidence_counter}"
                    evidence_counter += 1
                    all_evidence_by_id[cid] = ev

                assigned_eid = all_evidence_by_id[cid]["evidence_id"]
                if assigned_eid not in task_ev_ids:
                    task_ev_ids.append(assigned_eid)

                acc = ev.get("accession_number")
                if acc:
                    filing_refs.add(f"Accession: {acc}")

            # Determine task status
            if task_ev_ids:
                status = TaskStatus.COMPLETED.value
                findings = [
                    f"Retrieved {len(task_ev_ids)} evidence passages ({', '.join(task_ev_ids)})."
                ]
                missing = []
            else:
                status = TaskStatus.INSUFFICIENT_EVIDENCE.value
                findings = []
                missing = [f"No SEC filing passages found for {t_title}."]

            res_obj = ResearchTaskResult(
                task_id=t_id,
                question=t_desc,
                execution_status=status,
                retrieved_evidence=[
                    all_evidence_by_id[cid]
                    for cid in all_evidence_by_id
                    if all_evidence_by_id[cid]["evidence_id"] in task_ev_ids
                ],
                evidence_ids=task_ev_ids,
                filing_refs=sorted(filing_refs),
                reporting_periods=task.get("target_periods", []),
                findings=findings,
                missing_evidence=missing,
                warnings=task_warnings,
            )
            task_results.append(res_obj.model_dump())
            global_warnings.extend(task_warnings)

        consolidated_evidence = list(all_evidence_by_id.values())
        return consolidated_evidence, task_results, global_warnings

    def execute(self, state: FinovaAgentState) -> dict[str, Any]:
        """Execute hybrid search on single query or full research plan."""
        plan = state.get("research_plan")
        ticker = state.get("company_ticker")

        # If a structured plan is present, execute multi-task retrieval
        if plan and isinstance(plan, dict) and plan.get("tasks"):
            logger.info(
                "ResearchAgent: Executing multi-task research plan for %s", ticker
            )
            evidence, task_results, warnings = self.execute_plan(plan, ticker)
            all_warnings = list(state.get("warnings", [])) + warnings
            return {
                "retrieved_evidence": evidence,
                "task_results": task_results,
                "current_step": "research_agent",
                "warnings": all_warnings,
            }

        # Otherwise execute single query (Session 10 backward compatibility)
        query = state.get("research_query") or state.get("user_question", "")
        top_k = state.get("metadata", {}).get("top_k_evidence", 5)

        logger.info(
            "ResearchAgent querying single inquiry: '%s' (ticker=%s, top_k=%d)",
            query,
            ticker,
            top_k,
        )

        evidence_list, warnings = self._execute_single_query(
            query=query,
            ticker=ticker,
            top_k=top_k,
        )

        # Assign stable evidence IDs
        for idx, ev in enumerate(evidence_list, start=1):
            ev["evidence_id"] = f"E{idx}"

        all_warnings = list(state.get("warnings", [])) + warnings

        return {
            "retrieved_evidence": evidence_list,
            "current_step": "research_agent",
            "warnings": all_warnings,
        }
