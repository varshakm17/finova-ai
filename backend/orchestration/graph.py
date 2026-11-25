"""Compiled LangGraph Multi-Agent Orchestration Graph for Finova AI.

Connects Supervisor, Research Planner, Research Agent, Financial Analyst,
Research Coordinator, Report Agent, RAG, Verification, and Safe Response nodes
using typed state, conditional routing edges, bounded loops, and strict verification gates.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from langgraph.graph import END, START, StateGraph

from backend.agents.agent_models import (
    AgentExecutionStatus,
    AgentIntent,
    AgentRunRequest,
    AgentRunResponse,
    AgentWorkflowType,
    FinancialResearchReport,
    ReportGenerationRequest,
    ReportGenerationResponse,
    WorkflowStatus,
)
from backend.agents.financial_analyst_agent import FinancialAnalystAgent
from backend.agents.rag_agent import RAGAgent
from backend.agents.report_agent import ReportAgent
from backend.agents.research_agent import ResearchAgent
from backend.agents.research_coordinator import ResearchCoordinator
from backend.agents.research_planner import ResearchPlanner
from backend.agents.state import FinovaAgentState
from backend.agents.supervisor import SupervisorAgent
from backend.agents.verification_agent import VerificationAgent
from backend.data.storage import Database
from backend.orchestration.execution_tracer import ExecutionTracer
from backend.orchestration.workflow_config import WorkflowConfig
from backend.utils.logger import get_logger

logger = get_logger("orchestration_graph")


class FinovaOrchestrationEngine:
    """Manages compilation and execution of the multi-agent research graph."""

    def __init__(
        self,
        config: WorkflowConfig | None = None,
        database: Database | None = None,
        supervisor_agent: SupervisorAgent | None = None,
        research_planner: ResearchPlanner | None = None,
        research_agent: ResearchAgent | None = None,
        financial_analyst_agent: FinancialAnalystAgent | None = None,
        research_coordinator: ResearchCoordinator | None = None,
        report_agent: ReportAgent | None = None,
        rag_agent: RAGAgent | None = None,
        verification_agent: VerificationAgent | None = None,
    ) -> None:
        self.config = config or WorkflowConfig()
        self.db = database or Database()
        self.tracer = ExecutionTracer(database=self.db)

        # Agent adapters
        self.supervisor = supervisor_agent or SupervisorAgent()
        self.planner = research_planner or ResearchPlanner()
        self.research = research_agent or ResearchAgent()
        self.financial_analyst = financial_analyst_agent or FinancialAnalystAgent()
        self.coordinator = research_coordinator or ResearchCoordinator()
        self.report_agent = report_agent or ReportAgent()
        self.rag = rag_agent or RAGAgent()
        self.verifier = verification_agent or VerificationAgent()

        # Build and compile graph
        self.graph = self._build_graph()
        self.compiled_app = self.graph.compile()

    # =========================================================================
    # Node Implementations
    # =========================================================================

    def supervisor_node(self, state: FinovaAgentState) -> dict[str, Any]:
        """Classify inquiry, extract entities, and determine workflow routing."""
        req_id = state.get("request_id", str(uuid.uuid4()))
        step_idx = state.get("step_count", 0) + 1

        with self.tracer.trace_step(
            request_id=req_id,
            step_index=step_idx,
            agent_name=self.supervisor.agent_name,
            node_name="supervisor",
            input_summary=state.get("user_question"),
        ) as step:
            res = self.supervisor.execute(state)
            step.set_output(
                summary=f"Intent: {res.get('intent')}, Workflow: {res.get('workflow_type')}",
                metadata={"selected_agents": res.get("selected_agents")},
            )
            res["step_count"] = step_idx
            res["execution_trace"] = [step.finalize()]
            return res

    def research_planner_node(self, state: FinovaAgentState) -> dict[str, Any]:
        """Deconstruct research inquiry into ordered tasks and target filing sections."""
        req_id = state.get("request_id", str(uuid.uuid4()))
        step_idx = state.get("step_count", 0) + 1

        with self.tracer.trace_step(
            request_id=req_id,
            step_index=step_idx,
            agent_name=self.planner.agent_name,
            node_name="research_planner",
            input_summary=f"Objective: {state.get('user_question')} ({state.get('company_ticker')})",
        ) as step:
            res = self.planner.execute(state)
            plan_data = res.get("research_plan", {})
            task_count = len(plan_data.get("tasks", []))
            step.set_output(
                summary=f"Constructed plan with {task_count} sub-tasks.",
                metadata={
                    "task_count": task_count,
                    "plan_id": plan_data.get("plan_id"),
                },
            )

            # Persist plan to SQLite
            if plan_data:
                try:
                    self.db.save_research_plan(plan_data)
                except Exception as exc:
                    logger.warning("Failed to persist research plan: %s", exc)

            res["step_count"] = step_idx
            res["execution_trace"] = [step.finalize()]
            return res

    def research_node(self, state: FinovaAgentState) -> dict[str, Any]:
        """Perform hybrid retrieval and reranking for SEC filing excerpts."""
        req_id = state.get("request_id", str(uuid.uuid4()))
        step_idx = state.get("step_count", 0) + 1

        with self.tracer.trace_step(
            request_id=req_id,
            step_index=step_idx,
            agent_name=self.research.agent_name,
            node_name="research_agent",
            input_summary=f"Query: {state.get('user_question')} (Ticker: {state.get('company_ticker')})",
        ) as step:
            res = self.research.execute(state)
            ev_count = len(res.get("retrieved_evidence", []))
            task_res_count = len(res.get("task_results", []))
            summary_msg = (
                f"Executed multi-task plan ({task_res_count} tasks, {ev_count} chunks)."
                if task_res_count > 0
                else f"Retrieved {ev_count} evidence chunks."
            )
            step.set_output(
                summary=summary_msg,
                metadata={"evidence_count": ev_count, "task_count": task_res_count},
            )
            res["step_count"] = step_idx
            res["execution_trace"] = [step.finalize()]
            return res

    def financial_analyst_node(self, state: FinovaAgentState) -> dict[str, Any]:
        """Execute deterministic financial calculations on corporate XBRL facts."""
        req_id = state.get("request_id", str(uuid.uuid4()))
        step_idx = state.get("step_count", 0) + 1

        with self.tracer.trace_step(
            request_id=req_id,
            step_index=step_idx,
            agent_name=self.financial_analyst.agent_name,
            node_name="financial_analyst_agent",
            input_summary=f"Ticker: {state.get('company_ticker')}, Period: {state.get('reporting_period')}",
        ) as step:
            res = self.financial_analyst.execute(state)
            calc_count = len(res.get("calculation_results", []))
            analysis = res.get("financial_analysis") or {}
            trends_count = len(analysis.get("trends", []))
            step.set_output(
                summary=f"Calculated {calc_count} receipts and {trends_count} trends.",
                metadata={"receipts_count": calc_count, "trends_count": trends_count},
            )
            res["step_count"] = step_idx
            res["execution_trace"] = [step.finalize()]
            return res

    def merge_evidence_node(self, state: FinovaAgentState) -> dict[str, Any]:
        """Merge retrieved text evidence and calculation receipts for single-answer synthesis."""
        req_id = state.get("request_id", str(uuid.uuid4()))
        step_idx = state.get("step_count", 0) + 1

        with self.tracer.trace_step(
            request_id=req_id,
            step_index=step_idx,
            agent_name="ContextCoordinator",
            node_name="merge_evidence",
            input_summary="Consolidating multi-channel evidence",
        ) as step:
            ev_count = len(state.get("retrieved_evidence", []))
            calc_count = len(state.get("calculation_results", []))
            step.set_output(
                summary=f"Consolidated context: {ev_count} chunks, {calc_count} receipts.",
                metadata={"evidence_count": ev_count, "calc_count": calc_count},
            )
            return {
                "step_count": step_idx,
                "current_step": "merge_evidence",
                "execution_trace": [step.finalize()],
            }

    def research_coordinator_node(self, state: FinovaAgentState) -> dict[str, Any]:
        """Reconcile narrative evidence and calculation receipts into structured report findings."""
        req_id = state.get("request_id", str(uuid.uuid4()))
        step_idx = state.get("step_count", 0) + 1

        with self.tracer.trace_step(
            request_id=req_id,
            step_index=step_idx,
            agent_name=self.coordinator.agent_name,
            node_name="research_coordinator",
            input_summary="Consolidating research brief sections and findings",
        ) as step:
            res = self.coordinator.execute(state)
            cf = res.get("consolidated_findings", {})
            step.set_output(
                summary=f"Reconciled {cf.get('total_evidence_count', 0)} citations and {cf.get('total_calculation_count', 0)} calculations.",
                metadata=cf,
            )
            res["step_count"] = step_idx
            res["execution_trace"] = [step.finalize()]
            return res

    def report_agent_node(self, state: FinovaAgentState) -> dict[str, Any]:
        """Synthesize multi-section financial research brief with tables and citations."""
        req_id = state.get("request_id", str(uuid.uuid4()))
        step_idx = state.get("step_count", 0) + 1

        with self.tracer.trace_step(
            request_id=req_id,
            step_index=step_idx,
            agent_name=self.report_agent.agent_name,
            node_name="report_agent",
            input_summary=f"Compiling brief for {state.get('company_ticker')}",
        ) as step:
            res = self.report_agent.execute(state)
            rep = res.get("generated_report", {})
            sec_count = len(rep.get("sections", []))
            step.set_output(
                summary=f"Compiled research report '{rep.get('title')}' ({sec_count} sections).",
                metadata={"report_id": rep.get("report_id"), "sections": sec_count},
            )
            res["step_count"] = step_idx
            res["execution_trace"] = [step.finalize()]
            return res

    def rag_node(self, state: FinovaAgentState) -> dict[str, Any]:
        """Synthesize evidence-grounded research answer with strict citations."""
        req_id = state.get("request_id", str(uuid.uuid4()))
        step_idx = state.get("step_count", 0) + 1

        with self.tracer.trace_step(
            request_id=req_id,
            step_index=step_idx,
            agent_name=self.rag.agent_name,
            node_name="rag_agent",
            input_summary="Evidence-grounded synthesis",
        ) as step:
            res = self.rag.execute(state)
            ans = res.get("generated_answer", "")
            preview = (ans[:80] + "...") if len(ans) > 80 else ans
            step.set_output(
                summary=f"Synthesized answer: {preview}",
                metadata={"answer_length": len(ans)},
            )
            res["step_count"] = step_idx
            res["execution_trace"] = [step.finalize()]
            return res

    def verification_node(self, state: FinovaAgentState) -> dict[str, Any]:
        """Execute claim-level verification, numerical auditing, and contradiction detection."""
        req_id = state.get("request_id", str(uuid.uuid4()))
        step_idx = state.get("step_count", 0) + 1

        with self.tracer.trace_step(
            request_id=req_id,
            step_index=step_idx,
            agent_name=self.verifier.agent_name,
            node_name="verification_agent",
            input_summary="Auditing factual and numerical claims",
        ) as step:
            res = self.verifier.execute(state)
            vr = res.get("verification_result", {})
            v_status = vr.get("overall_status", "UNKNOWN")
            is_valid = vr.get("is_valid", True)
            step_status = (
                AgentExecutionStatus.SUCCESS.value
                if is_valid
                else AgentExecutionStatus.WARNING.value
            )
            step.set_output(
                summary=f"Verification status: {v_status} (is_valid={is_valid})",
                metadata={"verification_status": v_status, "is_valid": is_valid},
                status=step_status,
            )
            res["step_count"] = step_idx
            res["execution_trace"] = [step.finalize()]
            return res

    def safe_response_node(self, state: FinovaAgentState) -> dict[str, Any]:
        """Produce safe, compliant explanation for unsupported or verification-failed queries."""
        req_id = state.get("request_id", str(uuid.uuid4()))
        step_idx = state.get("step_count", 0) + 1

        with self.tracer.trace_step(
            request_id=req_id,
            step_index=step_idx,
            agent_name="SafetyGuardrail",
            node_name="safe_response",
            input_summary="Executing safety/rejection protocol",
        ) as step:
            intent = state.get("intent")
            vr = state.get("verification_result") or {}

            if intent == AgentIntent.UNSUPPORTED_OR_AMBIGUOUS.value:
                final_text = (
                    "Finova AI is a regulatory SEC financial research assistant designed to answer "
                    "factual corporate financial questions using statutory SEC filings and deterministic calculations. "
                    "We do not provide speculative trading advice, stock price predictions, buy/sell recommendations, "
                    "or answers to non-financial inquiries."
                )
                status_code = WorkflowStatus.REJECTED.value
            elif vr.get("overall_status") == "REJECTED" or vr.get("is_valid") is False:
                final_text = (
                    "The generated research response failed strict factual anti-hallucination verification "
                    "against statutory SEC evidence (detected unsupported claims, numerical discrepancies, "
                    "or temporal inconsistencies). To preserve financial integrity, the preliminary response has been withheld."
                )
                status_code = WorkflowStatus.REJECTED.value
            else:
                final_text = "The inquiry could not be completed within statutory safety parameters."
                status_code = WorkflowStatus.FAILED.value

            step.set_output(
                summary=final_text[:100], status=AgentExecutionStatus.SUCCESS.value
            )
            return {
                "final_answer": final_text,
                "status": status_code,
                "current_step": "safe_response",
                "step_count": step_idx,
                "execution_trace": [step.finalize()],
            }

    # =========================================================================
    # Conditional Routing Logic
    # =========================================================================

    def _route_supervisor(self, state: FinovaAgentState) -> str:
        """Route from supervisor to appropriate agent based on classified intent."""
        intent = state.get("intent")
        workflow = state.get("workflow_type")

        if (
            intent == AgentIntent.REPORT_GENERATION.value
            or workflow == AgentWorkflowType.FINANCIAL_RESEARCH_REPORT.value
        ):
            return "research_planner"

        if intent == AgentIntent.UNSUPPORTED_OR_AMBIGUOUS.value:
            return "safe_response"
        if intent == AgentIntent.FINANCIAL_ANALYSIS.value:
            return "financial_analyst_agent"
        if intent in (
            AgentIntent.GENERAL_RESEARCH.value,
            AgentIntent.COMBINED_ANALYSIS.value,
            AgentIntent.COMPARATIVE_RESEARCH.value,
        ):
            return "research_agent"
        return "safe_response"

    def _route_research(self, state: FinovaAgentState) -> str:
        """Route from research agent."""
        intent = state.get("intent")
        workflow = state.get("workflow_type")

        if (
            intent == AgentIntent.REPORT_GENERATION.value
            or workflow == AgentWorkflowType.FINANCIAL_RESEARCH_REPORT.value
        ):
            return "financial_analyst_agent"

        if intent in (
            AgentIntent.COMBINED_ANALYSIS.value,
            AgentIntent.COMPARATIVE_RESEARCH.value,
        ):
            return "financial_analyst_agent"
        return "merge_evidence"

    def _route_financial_analyst(self, state: FinovaAgentState) -> str:
        """Route from financial analyst agent."""
        intent = state.get("intent")
        workflow = state.get("workflow_type")

        if (
            intent == AgentIntent.REPORT_GENERATION.value
            or workflow == AgentWorkflowType.FINANCIAL_RESEARCH_REPORT.value
        ):
            return "research_coordinator"
        return "merge_evidence"

    def _route_verification(self, state: FinovaAgentState) -> str:
        """Route from verification: if rejected, route to safe_response; else complete."""
        vr = state.get("verification_result") or {}
        is_valid = vr.get("is_valid", True)
        status_val = vr.get("overall_status", "")

        if not is_valid or status_val == "REJECTED":
            return "safe_response"
        return "complete"

    # =========================================================================
    # Graph Construction
    # =========================================================================

    def _build_graph(self) -> StateGraph:
        """Assemble the Finova multi-agent StateGraph topology."""
        graph = StateGraph(FinovaAgentState)

        # 1. Add nodes
        graph.add_node("supervisor", self.supervisor_node)
        graph.add_node("research_planner", self.research_planner_node)
        graph.add_node("research_agent", self.research_node)
        graph.add_node("financial_analyst_agent", self.financial_analyst_node)
        graph.add_node("merge_evidence", self.merge_evidence_node)
        graph.add_node("research_coordinator", self.research_coordinator_node)
        graph.add_node("report_agent", self.report_agent_node)
        graph.add_node("rag_agent", self.rag_node)
        graph.add_node("verification_agent", self.verification_node)
        graph.add_node("safe_response", self.safe_response_node)

        # 2. Add edges
        graph.add_edge(START, "supervisor")

        graph.add_conditional_edges(
            "supervisor",
            self._route_supervisor,
            {
                "research_planner": "research_planner",
                "research_agent": "research_agent",
                "financial_analyst_agent": "financial_analyst_agent",
                "safe_response": "safe_response",
            },
        )

        graph.add_edge("research_planner", "research_agent")

        graph.add_conditional_edges(
            "research_agent",
            self._route_research,
            {
                "financial_analyst_agent": "financial_analyst_agent",
                "merge_evidence": "merge_evidence",
            },
        )

        graph.add_conditional_edges(
            "financial_analyst_agent",
            self._route_financial_analyst,
            {
                "research_coordinator": "research_coordinator",
                "merge_evidence": "merge_evidence",
            },
        )

        graph.add_edge("merge_evidence", "rag_agent")
        graph.add_edge("rag_agent", "verification_agent")

        graph.add_edge("research_coordinator", "report_agent")
        graph.add_edge("report_agent", "verification_agent")

        graph.add_conditional_edges(
            "verification_agent",
            self._route_verification,
            {
                "complete": END,
                "safe_response": "safe_response",
            },
        )

        graph.add_edge("safe_response", END)

        return graph

    # =========================================================================
    # Execution Runners
    # =========================================================================

    def run(self, request: AgentRunRequest) -> AgentRunResponse:
        """Execute the multi-agent graph with end-to-end tracing and persistence."""
        t0 = time.perf_counter()
        req_id = str(uuid.uuid4())
        logger.info("Initiating multi-agent run [%s]: '%s'", req_id, request.question)

        # Initialize shared graph state
        initial_state: FinovaAgentState = {
            "request_id": req_id,
            "user_question": request.question,
            "company_ticker": request.company_ticker,
            "company_name": None,
            "reporting_period": request.reporting_period,
            "intent": None,
            "workflow_type": None,
            "selected_agents": [],
            "research_query": None,
            "retrieved_evidence": [],
            "calculation_results": [],
            "generated_answer": None,
            "verification_result": None,
            "final_answer": None,
            "execution_trace": [],
            "errors": [],
            "warnings": [],
            "current_step": "init",
            "status": WorkflowStatus.IN_PROGRESS.value,
            "step_count": 0,
            "retry_count": 0,
            "mock_llm_response": request.mock_llm_response,
            "metadata": {
                "max_steps": request.max_steps,
                "timeout_seconds": request.timeout_seconds,
            },
        }

        # Save initial workflow record
        try:
            self.db.save_workflow_run(
                {
                    "request_id": req_id,
                    "user_question": request.question,
                    "company_ticker": request.company_ticker,
                    "intent": "UNKNOWN",
                    "workflow_type": "UNKNOWN",
                    "status": WorkflowStatus.IN_PROGRESS.value,
                }
            )
        except Exception as exc:
            logger.warning("Failed to record initial workflow in DB: %s", exc)

        # Execute LangGraph app
        final_state = initial_state
        try:
            final_state = self.compiled_app.invoke(initial_state)
        except Exception as exc:  # noqa: BLE001
            logger.error("LangGraph invocation failed: %s", exc, exc_info=True)
            final_state["errors"] = final_state.get("errors", []) + [str(exc)]
            final_state["status"] = WorkflowStatus.FAILED.value
            final_state["final_answer"] = (
                f"Workflow execution encountered an unexpected error: {exc}"
            )

        duration_ms = round((time.perf_counter() - t0) * 1000, 2)
        final_status = final_state.get("status", WorkflowStatus.COMPLETED.value)
        if final_status == WorkflowStatus.IN_PROGRESS.value:
            final_status = WorkflowStatus.COMPLETED.value

        # Persist report if one was generated
        if final_state.get("generated_report"):
            try:
                self.db.save_research_report(final_state["generated_report"])
            except Exception as exc:
                logger.warning("Failed to persist generated report in DB: %s", exc)

        # Build response container
        trace_events = [
            self.tracer.to_event_model(ev)
            for ev in final_state.get("execution_trace", [])
        ]

        vr = final_state.get("verification_result") or {}
        v_status = vr.get("overall_status")

        response = AgentRunResponse(
            request_id=req_id,
            question=request.question,
            company_ticker=final_state.get("company_ticker"),
            intent=final_state.get("intent", AgentIntent.GENERAL_RESEARCH.value),
            workflow_type=final_state.get("workflow_type", "default"),
            status=final_status,
            final_answer=final_state.get("final_answer"),
            verification_status=v_status,
            retrieved_evidence_count=len(final_state.get("retrieved_evidence", [])),
            calculation_receipts_count=len(final_state.get("calculation_results", [])),
            total_duration_ms=duration_ms,
            trace=trace_events,
            warnings=final_state.get("warnings", []),
            errors=final_state.get("errors", []),
        )

        # Update persisted workflow run
        try:
            self.db.save_workflow_run(
                {
                    "request_id": req_id,
                    "user_question": request.question,
                    "company_ticker": final_state.get("company_ticker"),
                    "intent": response.intent,
                    "workflow_type": response.workflow_type,
                    "status": response.status,
                    "final_answer": response.final_answer,
                    "verification_status": response.verification_status,
                    "retrieved_evidence_count": response.retrieved_evidence_count,
                    "calculation_receipts_count": response.calculation_receipts_count,
                    "total_duration_ms": duration_ms,
                    "error_message": "; ".join(response.errors)
                    if response.errors
                    else None,
                }
            )
        except Exception as exc:
            logger.warning("Failed to persist final workflow status to DB: %s", exc)

        return response

    def run_report(self, request: ReportGenerationRequest) -> ReportGenerationResponse:
        """Execute autonomous financial research report workflow and persist deliverable."""
        t0 = time.perf_counter()
        req_id = str(uuid.uuid4())
        logger.info(
            "Initiating autonomous report run [%s]: '%s' (ticker=%s)",
            req_id,
            request.question,
            request.ticker,
        )

        initial_state: FinovaAgentState = {
            "request_id": req_id,
            "user_question": request.question,
            "company_ticker": request.ticker,
            "company_name": request.company_name,
            "reporting_period": request.reporting_period,
            "intent": AgentIntent.REPORT_GENERATION.value,
            "workflow_type": AgentWorkflowType.FINANCIAL_RESEARCH_REPORT.value,
            "selected_agents": [
                "SupervisorAgent",
                "ResearchPlanner",
                "ResearchAgent",
                "FinancialAnalystAgent",
                "ResearchCoordinator",
                "ReportAgent",
                "VerificationAgent",
            ],
            "research_query": None,
            "retrieved_evidence": [],
            "calculation_results": [],
            "generated_answer": None,
            "verification_result": None,
            "final_answer": None,
            "execution_trace": [],
            "errors": [],
            "warnings": [],
            "current_step": "init",
            "status": WorkflowStatus.IN_PROGRESS.value,
            "step_count": 0,
            "retry_count": 0,
            "mock_llm_response": request.mock_llm_response,
            "output_format": request.output_format,
            "metadata": {
                "max_steps": request.max_steps,
                "timeout_seconds": request.timeout_seconds,
            },
        }

        # Save initial workflow record to satisfy foreign key constraints for execution events
        try:
            self.db.save_workflow_run(
                {
                    "request_id": req_id,
                    "user_question": request.question,
                    "company_ticker": request.ticker,
                    "intent": AgentIntent.REPORT_GENERATION.value,
                    "workflow_type": AgentWorkflowType.FINANCIAL_RESEARCH_REPORT.value,
                    "status": WorkflowStatus.IN_PROGRESS.value,
                }
            )
        except Exception as exc:
            logger.warning("Failed to record initial report workflow in DB: %s", exc)

        # Execute LangGraph app
        final_state = initial_state
        try:
            final_state = self.compiled_app.invoke(initial_state)
        except Exception as exc:  # noqa: BLE001
            logger.error("Report workflow invocation failed: %s", exc, exc_info=True)
            final_state["errors"] = final_state.get("errors", []) + [str(exc)]
            final_state["status"] = WorkflowStatus.FAILED.value

        duration_ms = round((time.perf_counter() - t0) * 1000, 2)
        final_status = final_state.get("status", WorkflowStatus.COMPLETED.value)
        if final_status == WorkflowStatus.IN_PROGRESS.value:
            final_status = WorkflowStatus.COMPLETED.value

        generated_rep_dict = final_state.get("generated_report")
        report_obj: FinancialResearchReport | None = None
        report_id = str(uuid.uuid4())

        if generated_rep_dict:
            try:
                report_obj = FinancialResearchReport.model_validate(generated_rep_dict)
                report_id = report_obj.report_id
                # Persist to database
                self.db.save_research_report(generated_rep_dict)
            except Exception as exc:
                logger.warning(
                    "Failed to validate or persist report deliverable: %s", exc
                )

        plan = final_state.get("research_plan", {})
        plan_summary = (
            f"Executed research plan with {len(plan.get('tasks', []))} tasks across {len(plan.get('target_periods', []))} periods."
            if isinstance(plan, dict) and plan.get("tasks")
            else "Autonomous research plan executed."
        )

        trace_events = [
            self.tracer.to_event_model(ev)
            for ev in final_state.get("execution_trace", [])
        ]

        vr = (
            final_state.get("verification_result")
            or final_state.get("report_verification")
            or {}
        )
        v_status = vr.get("overall_status", "UNKNOWN")

        return ReportGenerationResponse(
            request_id=req_id,
            report_id=report_id,
            status=final_status,
            verification_status=v_status,
            plan_summary=plan_summary,
            report=report_obj,
            markdown_content=final_state.get("report_markdown"),
            html_content=final_state.get("report_html"),
            total_sections=len(report_obj.sections) if report_obj else 0,
            total_evidence_cited=sum(
                1 for r in report_obj.references if r.ref_type != "calculation_receipt"
            )
            if report_obj
            else 0,
            total_calculations_cited=sum(
                1 for r in report_obj.references if r.ref_type == "calculation_receipt"
            )
            if report_obj
            else len(final_state.get("calculation_results", [])),
            execution_time_ms=duration_ms,
            trace=trace_events,
            warnings=final_state.get("warnings", []),
            errors=final_state.get("errors", []),
        )


# Global singleton engine
_orchestration_engine: FinovaOrchestrationEngine | None = None


def get_orchestration_engine() -> FinovaOrchestrationEngine:
    """Retrieve or initialize the Finova orchestration engine singleton."""
    global _orchestration_engine
    if _orchestration_engine is None:
        _orchestration_engine = FinovaOrchestrationEngine()
    return _orchestration_engine


def create_finova_workflow() -> StateGraph:
    """Factory creating an uncompiled Finova multi-agent StateGraph."""
    engine = get_orchestration_engine()
    return engine.graph
