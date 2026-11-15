"""Supervisor Agent for Finova AI Multi-Agent Orchestration.

Responsible for query analysis, intent classification, company and period extraction,
workflow topology routing, and auditable decision logging.
"""

from __future__ import annotations

import re
from typing import Any

from backend.agents.agent_models import AgentIntent, AgentWorkflowType
from backend.agents.base_agent import BaseFinovaAgent
from backend.agents.state import FinovaAgentState
from backend.utils.logger import get_logger

logger = get_logger("supervisor")

# Known company name to ticker mapping
COMPANY_MAP = {
    "apple": "AAPL",
    "microsoft": "MSFT",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "amazon": "AMZN",
    "tesla": "TSLA",
    "nvidia": "NVDA",
    "meta": "META",
    "netflix": "NFLX",
}

# Regex for common tickers
TICKER_REGEX = re.compile(r"\b([A-Z]{1,5})\b")

# Regex for fiscal periods (e.g., FY2023, 2023, Q3 2022, FY 2021)
PERIOD_REGEX = re.compile(
    r"\b(FY\s*\d{4}|\d{4}|Q[1-4](?:\s*(?:of\s*)?\d{4})?)\b", re.IGNORECASE
)

# Intent classification keywords
TRADING_ADVICE_KEYWORDS = {
    "buy",
    "sell",
    "hold",
    "invest in",
    "should i buy",
    "should i sell",
    "stock price target",
    "price target",
    "predict",
    "forecast stock",
    "crypto",
    "bitcoin",
    "moon",
    "short squeeze",
    "recommend stock",
}

FINANCIAL_ANALYSIS_KEYWORDS = {
    "margin",
    "ratio",
    "revenue",
    "net income",
    "operating income",
    "gross profit",
    "ebitda",
    "pe ratio",
    "debt",
    "equity",
    "cash flow",
    "free cash flow",
    "roe",
    "roa",
    "current ratio",
    "quick ratio",
    "eps",
    "earnings per share",
    "assets",
    "liabilities",
    "gross margin",
    "operating margin",
    "net profit margin",
}

QUALITATIVE_RESEARCH_KEYWORDS = {
    "strategy",
    "risk",
    "risks",
    "competition",
    "business model",
    "management",
    "overview",
    "legal proceedings",
    "md&a",
    "discussion and analysis",
    "regulatory",
    "headwinds",
    "catalyst",
    "products",
    "services",
    "threats",
    "opportunities",
    "governance",
}

COMPARATIVE_KEYWORDS = {
    "compare",
    "versus",
    "vs",
    "against",
    "between",
    "peer",
    "competitor",
}

COMMON_ACRONYM_STOPWORDS = {
    "A",
    "I",
    "AND",
    "OR",
    "THE",
    "FOR",
    "IN",
    "ON",
    "AT",
    "TO",
    "OF",
    "BY",
    "IS",
    "ARE",
    "WAS",
    "WERE",
    "WHAT",
    "HOW",
    "WHY",
    "CAN",
    "DID",
    "DO",
    "SEC",
    "CEO",
    "CFO",
    "USA",
    "USD",
    "GDP",
    "LLM",
    "AI",
    "MD",
    "MDA",
    "GAAP",
    "IFRS",
    "ESG",
    "KPI",
    "CAGR",
    "EBITDA",
    "EBIT",
    "EPS",
    "ROA",
    "ROE",
    "PE",
    "PB",
    "RRF",
    "BM25",
    "FAISS",
    "RAG",
    "ITEM",
    "FY",
    "Q1",
    "Q2",
    "Q3",
    "Q4",
}


class SupervisorAgent(BaseFinovaAgent):
    """Supervisor Agent that analyzes questions, assigns intent, and directs workflows."""

    def __init__(self) -> None:
        super().__init__(
            agent_name="SupervisorAgent",
            description="Supervisor agent that analyzes financial inquiries, classifies intent, extracts entities, and selects workflows.",
        )

    def extract_entities(self, text: str) -> tuple[str | None, str | None, list[str]]:
        """Extract company ticker, reporting period, and detected tickers from question text."""
        lower_text = text.lower()
        extracted_ticker: str | None = None
        extracted_period: str | None = None
        detected_tickers: list[str] = []

        # Check for company names
        for comp_name, tick in COMPANY_MAP.items():
            if re.search(rf"\b{comp_name}\b", lower_text):
                detected_tickers.append(tick)

        # Check for raw uppercase tickers
        for match in TICKER_REGEX.finditer(text):
            candidate = match.group(1).upper()
            if candidate not in COMMON_ACRONYM_STOPWORDS:
                if candidate not in detected_tickers:
                    detected_tickers.append(candidate)

        if detected_tickers:
            extracted_ticker = detected_tickers[0]

        # Check for period
        period_match = PERIOD_REGEX.search(text)
        if period_match:
            extracted_period = period_match.group(1).upper().replace(" ", "")

        return extracted_ticker, extracted_period, detected_tickers

    def classify_intent(
        self,
        question: str,
        detected_tickers: list[str],
    ) -> tuple[AgentIntent, AgentWorkflowType, list[str], str]:
        """Classify inquiry into one of the 5 defined intents with reasoning."""
        lower_q = question.lower()

        # 1. Check for Unsupported / Ambiguous / Trading Advice
        for kw in TRADING_ADVICE_KEYWORDS:
            if re.search(rf"\b{re.escape(kw)}\b", lower_q):
                reason = (
                    f"Identified unsupported investment/trading advice keyword: '{kw}'."
                )
                return (
                    AgentIntent.UNSUPPORTED_OR_AMBIGUOUS,
                    AgentWorkflowType.SAFE_REJECTION,
                    ["safe_response"],
                    reason,
                )

        # If question is too short or lacks financial meaning
        if len(question.strip().split()) < 3 and not detected_tickers:
            return (
                AgentIntent.UNSUPPORTED_OR_AMBIGUOUS,
                AgentWorkflowType.SAFE_REJECTION,
                ["safe_response"],
                "Question is ambiguous or lacks sufficient financial context.",
            )

        # 2. Check for Comparative Research
        has_comparative_kw = any(
            re.search(rf"\b{re.escape(kw)}\b", lower_q) for kw in COMPARATIVE_KEYWORDS
        )
        if (len(detected_tickers) >= 2) or (
            has_comparative_kw and len(detected_tickers) >= 1
        ):
            reason = f"Detected comparative inquiry involving multiple entities/comparative term ({detected_tickers})."
            return (
                AgentIntent.COMPARATIVE_RESEARCH,
                AgentWorkflowType.COMPARATIVE_ANALYSIS,
                [
                    "research_agent",
                    "financial_analyst_agent",
                    "rag_agent",
                    "verification_agent",
                ],
                reason,
            )

        # 3. Check for Financial Analysis vs Qualitative Research vs Combined
        found_fin_kw = [
            kw
            for kw in FINANCIAL_ANALYSIS_KEYWORDS
            if re.search(rf"\b{re.escape(kw)}\b", lower_q)
        ]
        found_qual_kw = [
            kw
            for kw in QUALITATIVE_RESEARCH_KEYWORDS
            if re.search(rf"\b{re.escape(kw)}\b", lower_q)
        ]

        if found_fin_kw and found_qual_kw:
            reason = (
                f"Combined inquiry detected with financial terms {found_fin_kw[:3]} "
                f"and qualitative research terms {found_qual_kw[:3]}."
            )
            return (
                AgentIntent.COMBINED_ANALYSIS,
                AgentWorkflowType.COMBINED_ANALYSIS,
                [
                    "research_agent",
                    "financial_analyst_agent",
                    "rag_agent",
                    "verification_agent",
                ],
                reason,
            )

        if found_fin_kw:
            reason = f"Financial analysis inquiry detected with metrics keywords: {found_fin_kw[:3]}."
            return (
                AgentIntent.FINANCIAL_ANALYSIS,
                AgentWorkflowType.FINANCIAL_ONLY,
                ["financial_analyst_agent", "rag_agent", "verification_agent"],
                reason,
            )

        # Default to general qualitative research
        reason = (
            "General qualitative SEC research inquiry (business, risks, operations)."
        )
        return (
            AgentIntent.GENERAL_RESEARCH,
            AgentWorkflowType.RESEARCH_ONLY,
            ["research_agent", "rag_agent", "verification_agent"],
            reason,
        )

    def execute(self, state: FinovaAgentState) -> dict[str, Any]:
        """Classify inquiry, extract entities, and determine workflow routing."""
        question = state.get("user_question", "")
        extracted_ticker, extracted_period, detected_tickers = self.extract_entities(
            question
        )

        # Prioritize explicit ticker/period from initial state if present
        ticker = state.get("company_ticker") or extracted_ticker
        period = state.get("reporting_period") or extracted_period

        intent, workflow_type, selected_agents, routing_reason = self.classify_intent(
            question, detected_tickers
        )

        trace_summary = (
            f"Classified intent as {intent.value} -> workflow {workflow_type.value}. "
            f"Ticker={ticker}, Period={period}. Selected agents: {selected_agents}."
        )

        logger.info("Supervisor: %s", trace_summary)

        return {
            "intent": intent.value,
            "workflow_type": workflow_type.value,
            "selected_agents": selected_agents,
            "company_ticker": ticker,
            "reporting_period": period,
            "current_step": "supervisor",
            "metadata": {
                **state.get("metadata", {}),
                "routing_reason": routing_reason,
                "detected_tickers": detected_tickers,
            },
        }
