"""Autonomous Research Planner for Finova AI.

Converts broad financial research requests and report generation objectives into
structured, executable research plans with discrete tasks, expected sections, and metrics.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from backend.agents.agent_models import (
    ReportSectionPlan,
    ResearchPlan,
    ResearchPlanValidation,
    ResearchTask,
    TaskType,
)
from backend.agents.base_agent import BaseFinovaAgent
from backend.agents.state import FinovaAgentState
from backend.agents.supervisor import SupervisorAgent
from backend.data.company_service import CompanyService
from backend.llm import get_llm_provider
from backend.llm.llm_provider import LLMProvider
from backend.utils.logger import get_logger
from backend.verification.period_verifier import normalize_period
from config.settings import Settings, get_settings

logger = get_logger("research_planner")

# Standard report sections
DEFAULT_REPORT_SECTIONS = [
    ReportSectionPlan(
        section_key="executive_summary",
        title="Executive Summary",
        order_index=1,
        required_data_sources=["findings_summary", "key_metrics"],
        description="High-level overview of company, objective, core findings, and limitations.",
    ),
    ReportSectionPlan(
        section_key="company_overview",
        title="Company Overview",
        order_index=2,
        required_data_sources=["ITEM_1", "sec_filings"],
        description="Business description, segments, and operating model.",
    ),
    ReportSectionPlan(
        section_key="financial_performance",
        title="Financial Performance Analysis",
        order_index=3,
        required_data_sources=["calculation_receipts", "metric_trends"],
        description="Revenue growth, profitability, margins, and cash flow dynamics.",
    ),
    ReportSectionPlan(
        section_key="historical_comparison",
        title="Historical Financial Comparison",
        order_index=4,
        required_data_sources=["metric_comparisons", "multi_year_receipts"],
        description="Period-by-period comparative table and significant percentage shifts.",
    ),
    ReportSectionPlan(
        section_key="business_operations_mda",
        title="Business Operations & Management Discussion",
        order_index=5,
        required_data_sources=["ITEM_7"],
        description="Operational milestones, headwinds, and management performance explanations.",
    ),
    ReportSectionPlan(
        section_key="risk_factors",
        title="Risk Factor Analysis",
        order_index=6,
        required_data_sources=["ITEM_1A"],
        description="Statutory business risks, macroeconomic threats, and operational challenges.",
    ),
    ReportSectionPlan(
        section_key="key_findings",
        title="Key Findings",
        order_index=7,
        required_data_sources=["consolidated_evidence"],
        description="Evidence-backed strategic takeaways, strengths, and risks.",
    ),
    ReportSectionPlan(
        section_key="conclusion",
        title="Conclusion",
        order_index=8,
        required_data_sources=["all_sections"],
        description="Summary synthesis and research caveats.",
    ),
    ReportSectionPlan(
        section_key="sources_references",
        title="Sources & References",
        order_index=9,
        required_data_sources=["filing_metadata", "calculation_receipts"],
        description="Official SEC filing accession numbers, URLs, and evidence citations.",
    ),
]


class ResearchPlanner(BaseFinovaAgent):
    """Generates structured research plans to guide multi-agent execution."""

    def __init__(
        self,
        company_service: CompanyService | None = None,
        llm_provider: LLMProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        super().__init__(
            agent_name="ResearchPlanner",
            description="Decomposes research objectives into structured tasks, required metrics, and expected report sections.",
        )
        self.settings = settings or get_settings()
        self.company_service = company_service or CompanyService()
        self.llm = llm_provider or get_llm_provider(settings=self.settings)
        self.supervisor = SupervisorAgent()

    def extract_fiscal_years(self, text: str, default_year: int = 2023) -> list[int]:
        """Extract multi-year fiscal years mentioned in query (e.g. 'last 3 years', '2021 to 2023', 'FY2023')."""
        lower = text.lower()
        years_found: set[int] = set()

        # Look for explicit 4-digit years with or without FY prefix
        for m in re.finditer(r"(?:FY\s*)?(20[12]\d)\b", text, re.IGNORECASE):
            years_found.add(int(m.group(1)))

        # Look for phrases like "last 3 years", "past three years"
        multi_year_match = re.search(
            r"\b(?:last|past|over the past|over the last)\s+(\d+|two|three|four|five)\s+years?\b",
            lower,
        )
        if multi_year_match:
            num_map = {"two": 2, "three": 3, "four": 4, "five": 5}
            raw_num = multi_year_match.group(1)
            count = int(raw_num) if raw_num.isdigit() else num_map.get(raw_num, 3)
            # Default anchoring to 2023
            max_y = max(years_found) if years_found else default_year
            return sorted([max_y - i for i in range(count)])

        if years_found:
            return sorted(years_found)

        return [default_year]

    def create_plan(
        self,
        question: str,
        ticker: str | None = None,
        target_periods: list[str] | None = None,
        request_id: str | None = None,
    ) -> ResearchPlan:
        """Create a complete structured research plan using deterministic rules."""
        period_str = ", ".join(target_periods) if target_periods else None
        plan = self.build_deterministic_plan(
            question=question,
            request_id=request_id or str(uuid.uuid4()),
            ticker=ticker,
            period_str=period_str,
        )
        if target_periods:
            plan.target_periods = target_periods
        return plan

    def build_deterministic_plan(
        self,
        question: str,
        request_id: str,
        ticker: str | None = None,
        period_str: str | None = None,
    ) -> ResearchPlan:
        """Create a complete structured research plan using deterministic rules."""
        lower_q = question.lower()

        # Resolve ticker and company name
        extracted_ticker, extracted_period, detected_tickers = (
            self.supervisor.extract_entities(question)
        )
        final_ticker = ticker or extracted_ticker
        final_period = period_str or extracted_period

        company_name = "Target Company"
        cik = None
        missing_info: list[str] = []

        if final_ticker:
            try:
                comp_info = self.company_service.get_company_by_ticker(final_ticker)
                if comp_info:
                    company_name = comp_info.get("name", final_ticker)
                    cik = comp_info.get("cik")
            except Exception:
                company_name = final_ticker
        else:
            missing_info.append(
                "Company ticker could not be resolved from question or inputs."
            )

        final_period = normalize_period(final_period)
        fiscal_years = self.extract_fiscal_years(question)
        if not final_period and fiscal_years:
            final_period = (
                f"FY{fiscal_years[0]}"
                if len(fiscal_years) == 1
                else f"FY{fiscal_years[0]}-FY{fiscal_years[-1]}"
            )

        # Identify required metrics
        required_metrics = [
            "revenue_growth",
            "gross_profit_margin",
            "operating_profit_margin",
            "net_profit_margin",
            "operating_cash_flow_margin",
            "free_cash_flow",
        ]
        if "ratio" in lower_q or "liquidity" in lower_q:
            required_metrics.append("current_ratio")
        if "debt" in lower_q or "leverage" in lower_q:
            required_metrics.append("debt_to_equity_ratio")
        if "roe" in lower_q or "equity" in lower_q:
            required_metrics.append("return_on_equity")
        if "roa" in lower_q or "asset" in lower_q:
            required_metrics.append("return_on_assets")

        # Narrative topics
        narrative_topics = ["business_overview", "mda_performance", "risk_factors"]
        if "legal" in lower_q:
            narrative_topics.append("legal_proceedings")

        # Construct concrete research tasks
        tasks: list[ResearchTask] = []
        t1 = ResearchTask(
            task_id="task_1_retrieval",
            task_type=TaskType.FILING_RETRIEVAL,
            title="Retrieve Primary SEC Filings and Excerpts",
            description=f"Query SEC 10-K disclosures for {final_ticker or company_name} covering {final_period}.",
            target_sections=["ITEM_1", "ITEM_7", "ITEM_1A"],
            target_periods=[str(y) for y in fiscal_years],
        )
        t2 = ResearchTask(
            task_id="task_2_metrics",
            task_type=TaskType.METRIC_CALCULATION,
            title="Compute Deterministic Financial Metrics",
            description=f"Calculate revenue, profitability margins, and cash flow receipts for {final_ticker or company_name}.",
            target_metrics=required_metrics,
            target_periods=[str(y) for y in fiscal_years],
            dependencies=["task_1_retrieval"],
        )
        t3 = ResearchTask(
            task_id="task_3_trends",
            task_type=TaskType.TREND_ANALYSIS,
            title="Analyze Multi-Period Financial Trends",
            description=f"Compute directional trends and period-over-period deltas across {fiscal_years}.",
            target_metrics=required_metrics,
            target_periods=[str(y) for y in fiscal_years],
            dependencies=["task_2_metrics"],
        )
        t4 = ResearchTask(
            task_id="task_4_mda",
            task_type=TaskType.MDA_ANALYSIS,
            title="Analyze MD&A Operational Performance",
            description="Examine management explanations, revenue drivers, and segment performance.",
            target_sections=["ITEM_7"],
            dependencies=["task_1_retrieval"],
        )
        t_risk = ResearchTask(
            task_id="task_5_risks",
            task_type=TaskType.RISK_ANALYSIS,
            title="Identify and Evaluate Statutory Risk Factors",
            description="Examine Item 1A statutory risk disclosures and market uncertainties.",
            target_sections=["ITEM_1A"],
            dependencies=["task_1_retrieval"],
        )
        t5 = ResearchTask(
            task_id="task_6_synthesis",
            task_type=TaskType.SYNTHESIS,
            title="Consolidate Multi-Section Research Report",
            description="Assemble executive brief with citations, comparative tables, and key findings.",
            dependencies=[
                "task_2_metrics",
                "task_3_trends",
                "task_4_mda",
                "task_5_risks",
            ],
        )
        t6 = ResearchTask(
            task_id="task_7_verification",
            task_type=TaskType.VERIFICATION,
            title="Claim-Level Anti-Hallucination Audit",
            description="Verify all numerical metrics and citations across report sections.",
            dependencies=["task_6_synthesis"],
        )
        tasks.extend([t1, t2, t3, t4, t_risk, t5, t6])

        objective_text = f"Autonomous financial research brief for {company_name} ({final_ticker or 'N/A'}) covering {final_period}."

        is_valid = bool(final_ticker) and len(missing_info) == 0

        plan = ResearchPlan(
            plan_id=str(uuid.uuid4()),
            request_id=request_id,
            company_name=company_name,
            ticker=final_ticker,
            cik=cik,
            objective=objective_text,
            reporting_period=final_period,
            fiscal_years=fiscal_years,
            target_periods=[f"FY{y}" for y in fiscal_years],
            required_filing_types=["10-K"],
            required_metrics=required_metrics,
            narrative_topics=narrative_topics,
            expected_sections=DEFAULT_REPORT_SECTIONS,
            tasks=tasks,
            missing_information=missing_info,
            is_valid=is_valid,
            planning_method="deterministic",
            planning_rationale="Decomposed query into SEC filing retrieval, deterministic math, trend analysis, and verification.",
        )
        return plan

    def validate_plan(self, plan: ResearchPlan) -> ResearchPlanValidation:
        """Validate research plan completeness and statutory grounding."""
        issues: list[str] = []
        warnings: list[str] = []

        if not plan.ticker:
            issues.append("Missing company ticker symbol.")
        if not plan.fiscal_years:
            issues.append("No fiscal years specified for research.")
        if not plan.tasks:
            issues.append("Plan contains zero executable research tasks.")
        if not plan.required_metrics:
            warnings.append(
                "No financial metrics specified; report will be purely qualitative."
            )

        return ResearchPlanValidation(
            is_valid=len(issues) == 0,
            issues=issues,
            warnings=warnings,
        )

    def execute(self, state: FinovaAgentState) -> dict[str, Any]:
        """Execute autonomous research planning and update shared state."""
        question = state.get("user_question", "")
        req_id = state.get("request_id", str(uuid.uuid4()))
        ticker = state.get("company_ticker")
        period = state.get("reporting_period")

        logger.info(
            "ResearchPlanner: Developing research plan for '%s' (ticker=%s)",
            question,
            ticker,
        )

        plan = self.build_deterministic_plan(
            question=question,
            request_id=req_id,
            ticker=ticker,
            period_str=period,
        )

        validation = self.validate_plan(plan)
        plan_dict = plan.model_dump()
        plan_dict["is_valid"] = validation.is_valid

        warnings = list(state.get("warnings", [])) + validation.warnings
        errors = list(state.get("errors", [])) + validation.issues

        return {
            "research_plan": plan_dict,
            "company_ticker": plan.ticker,
            "company_name": plan.company_name,
            "reporting_period": plan.reporting_period,
            "current_step": "research_planner",
            "warnings": warnings,
            "errors": errors,
        }
