"""Finova AI — Streamlit Frontend Application.

Provides a financial intelligence interface with dark navy styling,
health diagnostics, SEC filing discovery, XBRL financial metrics,
and statutory filing HTML ingestion with section-aware chunk inspection.
"""

import sys
from pathlib import Path
from typing import Any

import httpx
import streamlit as st
import streamlit.components.v1 as components

# Ensure project root is in sys.path for relative imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.utils.logger import get_logger
from config.settings import get_settings

logger = get_logger("frontend")

# -----------------------------------------------------------------------------
# Page Configuration & Styling
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Finova AI — Financial Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
    /* Dark Navy & Financial Analytics Theme */
    :root {
        --bg-main: #0B132B;
        --bg-card: #1C2541;
        --bg-hover: #3A506B;
        --accent-teal: #00B4D8;
        --accent-emerald: #06D6A0;
        --text-primary: #F8FAFC;
        --text-secondary: #94A3B8;
        --border-color: #334155;
    }

    .stApp {
        background-color: var(--bg-main);
        color: var(--text-primary);
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    .finova-header {
        padding: 1.25rem 1.5rem;
        background: linear-gradient(135deg, #1C2541 0%, #0B132B 100%);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        margin-bottom: 1.5rem;
    }

    .finova-header h1 {
        margin: 0;
        font-size: 2.2rem;
        font-weight: 700;
        color: #F8FAFC;
        letter-spacing: -0.5px;
    }

    .finova-header p {
        margin: 0.5rem 0 0 0;
        color: var(--accent-teal);
        font-size: 1.05rem;
    }

    .card {
        background-color: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 10px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        transition: transform 0.15s ease-in-out;
    }

    .card:hover {
        border-color: var(--accent-teal);
    }

    .badge-active {
        display: inline-block;
        padding: 0.25rem 0.65rem;
        background-color: rgba(6, 214, 160, 0.15);
        color: var(--accent-emerald);
        border: 1px solid rgba(6, 214, 160, 0.4);
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
    }

    .badge-offline {
        display: inline-block;
        padding: 0.25rem 0.65rem;
        background-color: rgba(239, 68, 68, 0.15);
        color: #F87171;
        border: 1px solid rgba(239, 68, 68, 0.4);
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
    }

    .badge-planned {
        display: inline-block;
        padding: 0.25rem 0.65rem;
        background-color: rgba(0, 180, 216, 0.15);
        color: var(--accent-teal);
        border: 1px solid rgba(0, 180, 216, 0.4);
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
    }

    .metric-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: var(--text-primary);
    }

    .metric-label {
        font-size: 0.85rem;
        color: var(--text-secondary);
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Backend Health Verification
# -----------------------------------------------------------------------------
def check_backend_health(base_url: str) -> dict[str, Any] | None:
    """Query backend health check endpoint safely with a brief timeout."""
    try:
        response = httpx.get(f"{base_url}/health", timeout=1.2)
        if response.status_code == 200:
            return response.json()
    except (httpx.RequestError, httpx.HTTPStatusError):
        return None
    return None


# -----------------------------------------------------------------------------
# Application Layout & Views
# -----------------------------------------------------------------------------
def main() -> None:
    settings = get_settings()
    backend_url = f"http://{settings.HOST}:{settings.PORT}"
    health_data = check_backend_health(backend_url)

    # Sidebar
    with st.sidebar:
        st.markdown("### 📊 Finova AI")
        st.caption("Multi-Agent Financial Research & Intelligence")
        st.markdown("---")

        # System Status Indicator
        st.markdown("**System Status**")
        if health_data:
            st.markdown(
                f'<span class="badge-active">● Backend: Online (v{health_data.get("version", "0.1.0")})</span>',
                unsafe_allow_html=True,
            )
            st.caption(f"Connected to `{backend_url}`")
        else:
            st.markdown(
                '<span class="badge-offline">○ Backend: Offline</span>',
                unsafe_allow_html=True,
            )
            st.caption(f"Run `uvicorn backend.main:app` on port {settings.PORT}")

        st.markdown("---")

        # Navigation
        nav_selection = st.radio(
            "Navigation",
            options=[
                "Overview",
                "Autonomous Research Reports",
                "Multi-Agent Research",
                "Company Lookup & Ingestion (SEC)",
                "Hybrid Research Search (RRF)",
                "Retrieval Evaluation & Evidence Quality",
                "Financial Research Assistant",
                "Agent Architecture",
                "Configuration",
            ],
            index=0,
        )

        st.markdown("---")
        st.markdown("**SEC EDGAR Compliance**")
        st.caption(
            "SEC queries require a declared User-Agent. Configure your identifier in `.env` "
            "prior to making live SEC requests."
        )

    # Main Header
    st.markdown(
        """
        <div class="finova-header">
            <h1>Finova AI</h1>
            <p>Multi-Agent Financial Research and Intelligence System</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -------------------------------------------------------------------------
    # View 1: Overview
    # -------------------------------------------------------------------------
    if nav_selection == "Overview":
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(
                """
                <div class="card">
                    <div class="metric-label">Foundation Status</div>
                    <div class="metric-value">Session 11</div>
                    <p style="color: #94A3B8; font-size: 0.9rem; margin-top: 0.5rem;">
                        Autonomous Research Briefs & Multi-Section Report Generation
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown(
                """
                <div class="card">
                    <div class="metric-label">Claim Verification</div>
                    <div class="metric-value">Deterministic</div>
                    <p style="color: #94A3B8; font-size: 0.9rem; margin-top: 0.5rem;">
                        Exact numerical tolerances, reporting period audits, contradiction checks.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col3:
            st.markdown(
                """
                <div class="card">
                    <div class="metric-label">Citation Auditing</div>
                    <div class="metric-value">100% Traceable</div>
                    <p style="color: #94A3B8; font-size: 0.9rem; margin-top: 0.5rem;">
                        Every factual assertion requires verified [E1]/[C1] citations and EDGAR URLs.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("### 🎯 System Objectives & Core Capabilities")
        st.markdown(
            """
            Finova AI is engineered to automate rigorous, evidence-backed corporate financial analysis:
            
            - **Anti-Hallucination Verification**: Every sentence and factual claim is extracted, audited against cited SEC filings and deterministic calculation receipts, checking for numeric discrepancies, scale errors, and period mismatches.
            - **Evidence-Grounded Financial RAG**: Answer complex corporate finance queries with statutory passage citations ([E1]) and deterministic calculation receipts ([C1]).
            - **Deterministic Metric Engine**: Exact calculation of revenue growth, margins, liquidity, leverage, and free cash flows from structured XBRL facts. Arithmetic calculations are executed strictly by deterministic Python formulas, not LLMs.
            - **Hybrid IR & Reranking**: Reciprocal Rank Fusion (RRF) over FAISS dense vectors and BM25 sparse lexical tokens, refined with Cross-Encoder reranking.
            - **Automated SEC EDGAR Retrieval**: Programmatic acquisition of annual (10-K) and quarterly (10-Q) filings with section-aware chunking.
            """
        )

        st.info(
            "📌 **Session 11 Active**: Autonomous Financial Research Briefs & Multi-Section Report Generation is fully operational. "
            "Navigate to **Autonomous Research Reports** to plan, execute multi-task research, analyze longitudinal trends, "
            "and generate auditable reports in Markdown and HTML."
        )

    # -------------------------------------------------------------------------
    # View 2: Autonomous Research Reports (Session 11)
    # -------------------------------------------------------------------------
    elif nav_selection == "Autonomous Research Reports":
        st.markdown(
            "### 📑 Autonomous Financial Research Reports & Intelligence Briefs"
        )
        st.caption(
            "End-to-end autonomous research orchestration: deterministic task planning, multi-period trend computation, "
            "multi-section Markdown/HTML synthesis, and claim-level anti-hallucination verification."
        )

        with st.form("report_generation_form"):
            r_col1, r_col2 = st.columns([3, 1])
            with r_col1:
                rep_question = st.text_area(
                    "Research Objective / Brief Scope",
                    value="Analyze Apple's financial performance, profitability margins, revenue growth trends, and key operational risk factors.",
                    height=100,
                    help="Describe the research objective. The Research Planner will decompose this into specialized filing and calculation tasks.",
                )
            with r_col2:
                rep_ticker = st.text_input(
                    "Target Ticker",
                    value="AAPL",
                    placeholder="e.g. AAPL, MSFT, NVDA",
                )
                rep_period = st.text_input(
                    "Reporting Period",
                    value="FY2022-FY2023",
                    placeholder="e.g. FY2023, FY2022-FY2023",
                )
                rep_format = st.selectbox(
                    "Deliverable Format",
                    options=["markdown", "html"],
                    index=0,
                )

            with st.expander("⚙️ Advanced Parameters"):
                p1, p2 = st.columns(2)
                with p1:
                    rep_max_steps = st.slider("Max Execution Steps", 5, 30, 20)
                with p2:
                    rep_timeout = st.slider("Timeout (seconds)", 15, 300, 120)

            submitted_report = st.form_submit_button(
                "🚀 Generate Autonomous Financial Brief", use_container_width=True
            )

        if submitted_report:
            with st.spinner(
                "Executing autonomous research planning, task retrieval, trend calculation, and verification..."
            ):
                try:
                    payload = {
                        "question": rep_question,
                        "ticker": rep_ticker.strip().upper() if rep_ticker else None,
                        "reporting_period": rep_period.strip() if rep_period else None,
                        "output_format": rep_format,
                        "max_steps": rep_max_steps,
                        "timeout_seconds": rep_timeout,
                    }
                    resp = httpx.post(
                        f"{backend_url}/api/v1/reports/generate",
                        json=payload,
                        timeout=float(rep_timeout) + 10.0,
                    )
                    if resp.status_code == 200:
                        st.session_state["last_report"] = resp.json()
                        st.success(
                            "✅ Autonomous research report successfully generated and verified!"
                        )
                    else:
                        st.error(
                            f"Report generation failed ({resp.status_code}): {resp.text}"
                        )
                except Exception as exc:
                    st.error(f"Error communicating with backend API: {exc}")

        # Display Report Results
        last_rep = st.session_state.get("last_report")
        if last_rep:
            st.markdown("---")
            m1, m2, m3, m4, m5 = st.columns(5)
            v_stat = last_rep.get("verification_status", "UNKNOWN")
            is_verified = (
                "VERIFIED" in v_stat
                and "NOT" not in v_stat
                and "REJECTED" not in v_stat
            )

            with m1:
                st.metric("Report Status", last_rep.get("status", "completed").upper())
            with m2:
                st.metric("Verification", v_stat)
            with m3:
                st.metric("Sections", last_rep.get("total_sections", 0))
            with m4:
                st.metric("Statutory Sources", last_rep.get("total_evidence_cited", 0))
            with m5:
                dur_s = round(last_rep.get("execution_time_ms", 0) / 1000.0, 2)
                st.metric("Execution Time", f"{dur_s}s")

            # Report Navigation Tabs
            tab_report, tab_plan, tab_trends, tab_verification, tab_html = st.tabs(
                [
                    "📄 Full Research Brief",
                    "📋 Autonomous Research Plan",
                    "📈 Longitudinal Trends & Ratios",
                    "🛡️ Claim Verification Audit",
                    "🌐 Publication HTML View",
                ]
            )

            report_obj = last_rep.get("report") or {}

            with tab_report:
                md_content = last_rep.get("markdown_content") or report_obj.get(
                    "markdown_content", ""
                )
                if md_content:
                    st.markdown(md_content)
                    st.download_button(
                        "📥 Download Markdown Report (.md)",
                        data=md_content,
                        file_name=f"finova_report_{last_rep.get('report_id', 'brief')}.md",
                        mime="text/markdown",
                        use_container_width=True,
                    )
                else:
                    st.warning("No markdown content available.")

            with tab_plan:
                st.markdown("#### Autonomous Plan Execution Summary")
                st.info(last_rep.get("plan_summary", "Autonomous plan executed."))
                sections = report_obj.get("sections", [])
                if sections:
                    st.markdown("##### Target Sections & Coverage")
                    for sec in sections:
                        st.markdown(
                            f"- **{sec.get('title', 'Section')}** (Order: {sec.get('order_index', 0)}) — Status: `{sec.get('verification_status', 'VERIFIED')}`"
                        )

            with tab_trends:
                st.markdown(
                    "#### Deterministic Financial Calculations & Comparative Tables"
                )
                st.caption(
                    "Computed strictly with Python formulas from XBRL facts — Zero LLM arithmetic."
                )
                # Show sections that have tables
                for sec in report_obj.get("sections", []):
                    if sec.get("tables"):
                        for tbl in sec["tables"]:
                            st.markdown(f"##### {tbl.get('title')}")
                            headers = tbl.get("headers", [])
                            rows = tbl.get("rows", [])
                            if headers and rows:
                                st.table([dict(zip(headers, r)) for r in rows])

            with tab_verification:
                st.markdown("#### Anti-Hallucination Claim-Level Verification Audit")
                if is_verified:
                    st.success(
                        f"Audit Result: `{v_stat}` — All factual claims and numerical figures are grounded."
                    )
                else:
                    st.warning(
                        f"Audit Result: `{v_stat}` — Numerical discrepancies or unsupported assertions detected."
                    )

                refs = report_obj.get("references", [])
                if refs:
                    st.markdown("##### Auditable References & Citations")
                    for r in refs:
                        st.markdown(
                            f"- **`[{r.get('citation_id')}]` {r.get('filing_name', 'Source')}**: "
                            f"{r.get('description', '')} (Acc: `{r.get('accession_number', 'N/A')}`)"
                        )

            with tab_html:
                html_code = last_rep.get("html_content") or report_obj.get(
                    "html_content", ""
                )
                if html_code:
                    components.html(html_code, height=650, scrolling=True)
                    st.download_button(
                        "📥 Download HTML Report (.html)",
                        data=html_code,
                        file_name=f"finova_report_{last_rep.get('report_id', 'brief')}.html",
                        mime="text/html",
                        use_container_width=True,
                    )
                else:
                    st.info("HTML deliverable format was not generated for this run.")

        # Historical Reports Section
        st.markdown("---")
        st.markdown("### 🗄️ Historical Research Briefs")
        hist_col1, hist_col2 = st.columns([2, 1])
        with hist_col1:
            filter_ticker = st.text_input(
                "Filter by Ticker", value="", placeholder="e.g. AAPL"
            )
        with hist_col2:
            st.write("")
            st.write("")
            st.button("🔄 Refresh Reports", use_container_width=True)

        try:
            params = {}
            if filter_ticker.strip():
                params["ticker"] = filter_ticker.strip().upper()
            h_resp = httpx.get(
                f"{backend_url}/api/v1/reports", params=params, timeout=10.0
            )
            if h_resp.status_code == 200:
                past_reports = h_resp.json()
                if past_reports:
                    for rep_item in past_reports[:10]:
                        with st.expander(
                            f"Brief: {rep_item.get('title')} ({rep_item.get('reporting_period', 'N/A')}) - {rep_item.get('verification_status')}"
                        ):
                            st.write(f"**Report ID:** `{rep_item.get('report_id')}`")
                            st.write(f"**Created At:** {rep_item.get('created_at')}")
                            st.write(f"**Status:** {rep_item.get('status')}")
                            if st.button(
                                "Load Report", key=f"load_{rep_item.get('report_id')}"
                            ):
                                full_rep = httpx.get(
                                    f"{backend_url}/api/v1/reports/{rep_item.get('report_id')}"
                                ).json()
                                st.session_state["last_report"] = {
                                    "status": full_rep.get("status"),
                                    "verification_status": full_rep.get(
                                        "verification_status"
                                    ),
                                    "report": full_rep,
                                    "markdown_content": full_rep.get(
                                        "markdown_content"
                                    ),
                                    "html_content": full_rep.get("html_content"),
                                    "total_sections": len(full_rep.get("sections", [])),
                                    "total_evidence_cited": len(
                                        full_rep.get("references", [])
                                    ),
                                    "plan_summary": "Retrieved from persistent storage.",
                                }
                                st.rerun()
                else:
                    st.caption("No historical research briefs found.")
        except Exception as exc:
            st.caption(f"Unable to load historical reports: {exc}")

    # -------------------------------------------------------------------------
    # View 2: Multi-Agent Research (Session 10)
    # -------------------------------------------------------------------------
    elif nav_selection == "Multi-Agent Research":
        st.markdown("### 🤖 Multi-Agent Financial Research Orchestration (LangGraph)")
        st.caption(
            "Autonomous multi-agent execution coordinating Supervisor, Research, Financial Analyst, "
            "RAG Answer, and Anti-Hallucination Verification agents."
        )

        with st.form("agent_research_form"):
            q_col1, q_col2 = st.columns([3, 1])
            with q_col1:
                question_input = st.text_area(
                    "Financial Research Question",
                    value="What were Apple's primary revenue drivers and gross margin in fiscal year 2023?",
                    height=90,
                    help="Ask a complex research question. The Supervisor Agent will classify intent and coordinate specialized agents.",
                )
            with q_col2:
                ticker_input = st.text_input(
                    "Target Ticker (Optional)",
                    value="AAPL",
                    placeholder="e.g. AAPL, MSFT",
                )
                period_input = st.text_input(
                    "Target Period (Optional)",
                    value="FY2023",
                    placeholder="e.g. FY2023, 2023",
                )

            with st.expander("⚙️ Execution Configuration & Limits"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    max_steps_val = st.slider("Max Orchestration Steps", 3, 20, 10)
                with c2:
                    timeout_val = st.slider("Timeout (seconds)", 10, 180, 60)
                with c3:
                    mock_override = st.text_input(
                        "Mock LLM Response (Optional)",
                        value="",
                        help="Override for deterministic testing without live Ollama",
                    )

            run_btn = st.form_submit_button(
                "🚀 Run Multi-Agent Orchestration", type="primary"
            )

        if run_btn:
            if not question_input.strip():
                st.error("Please enter a research question.")
            else:
                with st.spinner("Executing LangGraph multi-agent orchestration..."):
                    payload = {
                        "question": question_input.strip(),
                        "company_ticker": ticker_input.strip().upper()
                        if ticker_input.strip()
                        else None,
                        "reporting_period": period_input.strip()
                        if period_input.strip()
                        else None,
                        "max_steps": max_steps_val,
                        "timeout_seconds": float(timeout_val),
                        "mock_llm_response": mock_override.strip()
                        if mock_override.strip()
                        else None,
                    }

                    agent_res = None
                    try:
                        resp = httpx.post(
                            f"{backend_url}/api/v1/agents/run",
                            json=payload,
                            timeout=float(timeout_val) + 5.0,
                        )
                        if resp.status_code == 200:
                            agent_res = resp.json()
                        else:
                            st.warning(
                                f"Backend HTTP {resp.status_code}: {resp.text}. Falling back to direct engine."
                            )
                    except Exception as exc:
                        st.info(
                            f"Backend offline ({exc}). Executing directly via Finova orchestration engine."
                        )

                    if agent_res is None:
                        try:
                            from backend.agents.agent_models import AgentRunRequest
                            from backend.orchestration.graph import (
                                get_orchestration_engine,
                            )

                            engine = get_orchestration_engine()
                            req_obj = AgentRunRequest(**payload)
                            agent_res = engine.run(req_obj).model_dump()
                        except Exception as e:
                            st.error(f"Execution failed: {e}")

                    if agent_res:
                        st.session_state["last_agent_run"] = agent_res

        last_run = st.session_state.get("last_agent_run")
        if last_run:
            st.markdown("---")
            st.markdown("#### 🎯 Orchestration Summary")

            # Status and Metrics Row
            m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)
            with m_col1:
                st.metric("Classified Intent", last_run.get("intent", "UNKNOWN"))
            with m_col2:
                st.metric("Workflow Route", last_run.get("workflow_type", "UNKNOWN"))
            with m_col3:
                st.metric("Status", last_run.get("status", "UNKNOWN"))
            with m_col4:
                st.metric(
                    "Execution Time", f"{last_run.get('total_duration_ms', 0):.1f} ms"
                )
            with m_col5:
                v_stat = last_run.get("verification_status") or "N/A"
                st.metric("Verification", v_stat)

            # Warning callouts if any
            if last_run.get("warnings"):
                with st.expander("⚠️ System & Retrieval Warnings", expanded=False):
                    for w in last_run["warnings"]:
                        st.caption(f"- {w}")

            # Execution Trace Visual Timeline
            st.markdown("#### ⏱️ Agent Execution Trace & Timeline")
            trace_events = last_run.get("trace", [])
            if trace_events:
                trace_rows = []
                for ev in trace_events:
                    st_val = ev.get("status", "SUCCESS")
                    badge = (
                        "✅ SUCCESS"
                        if st_val == "SUCCESS"
                        else ("⚠️ WARNING" if st_val == "WARNING" else "❌ FAILED")
                    )
                    trace_rows.append(
                        {
                            "Step": ev.get("step_index", 0),
                            "Agent Name": ev.get("agent_name", "N/A"),
                            "Node Name": ev.get("node_name", "N/A"),
                            "Duration (ms)": f"{ev.get('duration_ms', 0.0):.2f}",
                            "Status": badge,
                            "Input Summary": str(ev.get("input_summary") or "")[:60],
                            "Output Summary": str(ev.get("output_summary") or "")[:80],
                        }
                    )
                st.table(trace_rows)
            else:
                st.info("No trace events recorded.")

            # Grounded Answer Presentation
            st.markdown("#### 📄 Grounded Research Answer")
            final_ans = last_run.get("final_answer")
            if final_ans:
                st.markdown(
                    f"""
                    <div class="card" style="border-left: 4px solid var(--accent-teal); font-size: 1.05rem; line-height: 1.6;">
                        {final_ans}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.warning("No final answer produced by the multi-agent workflow.")

            # Detail Tabs
            tab_calcs, tab_evidence, tab_raw = st.tabs(
                [
                    f"🔢 Calculation Receipts ({last_run.get('calculation_receipts_count', 0)})",
                    f"📚 Statutory Evidence Passages ({last_run.get('retrieved_evidence_count', 0)})",
                    "🔍 Raw Execution Trace JSON",
                ]
            )

            with tab_calcs:
                st.caption(
                    "Deterministic mathematical metrics computed by Financial Analyst Agent."
                )
                st.info(
                    "Verified Python formulas applied directly to structured XBRL observations — Zero LLM arithmetic."
                )
                # Retrieve from storage if available
                req_id = last_run.get("request_id")
                st.caption(f"Workflow Request ID: `{req_id}`")

            with tab_evidence:
                st.caption(
                    "Excerpts retrieved from statutory SEC EDGAR filings with provenance."
                )
                st.caption(
                    f"Retrieved items: {last_run.get('retrieved_evidence_count', 0)}"
                )

            with tab_raw:
                st.json(last_run)

    # -------------------------------------------------------------------------
    # View 2: Company Lookup & Ingestion (SEC)
    # -------------------------------------------------------------------------
    elif nav_selection == "Company Lookup & Ingestion (SEC)":
        st.markdown("### 🏢 SEC EDGAR Company Lookup & Document Ingestion")
        st.caption(
            "Discover company filings, extract XBRL financial facts, and ingest primary 10-K/10-Q filings into text chunks."
        )

        col_search, col_btn = st.columns([3, 1])
        with col_search:
            search_ticker = (
                st.text_input(
                    "Company Ticker Symbol",
                    value="AAPL",
                    help="Enter a US stock ticker (e.g., AAPL, MSFT, NVDA).",
                )
                .strip()
                .upper()
            )
        with col_btn:
            st.write("")
            st.write("")
            search_clicked = st.button(
                "Query SEC Data", type="primary", use_container_width=True
            )

        if search_ticker and (search_clicked or "last_searched" in st.session_state):
            st.session_state["last_searched"] = search_ticker

            if not health_data:
                st.error(
                    "⚠️ FastAPI Backend is offline. Please start the backend service using: "
                    "`uvicorn backend.main:app --port 8000` to query live SEC data."
                )
            else:
                with st.spinner(f"Retrieving SEC data for {search_ticker}..."):
                    try:
                        # 1. Company Search / Metadata
                        meta_resp = httpx.get(
                            f"{backend_url}/api/v1/companies/{search_ticker}",
                            timeout=15.0,
                        )

                        if meta_resp.status_code == 404:
                            st.warning(
                                f"Company ticker '{search_ticker}' was not found in SEC EDGAR."
                            )
                        elif meta_resp.status_code != 200:
                            st.error(
                                f"Error ({meta_resp.status_code}): {meta_resp.text}"
                            )
                        else:
                            company_info = meta_resp.json()

                            # Display Company Profile Card
                            st.markdown(
                                f"""
                                <div class="card">
                                    <div style="display: flex; justify-content: space-between; align-items: center;">
                                        <h3 style="margin: 0; color: #F8FAFC;">{company_info.get("name")} ({company_info.get("ticker")})</h3>
                                        <span class="badge-active">CIK: {company_info.get("cik")}</span>
                                    </div>
                                    <p style="color: #94A3B8; margin-top: 0.5rem; margin-bottom: 0;">
                                        Industry: <strong>{company_info.get("sic_description") or "N/A"}</strong> (SIC: {company_info.get("sic") or "N/A"}) | 
                                        Fiscal Year End: <strong>{company_info.get("fiscal_year_end") or "N/A"}</strong> | 
                                        Location: <strong>{company_info.get("state_location") or "N/A"}</strong>
                                    </p>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )

                            (
                                tab_ingest,
                                tab_filings,
                                tab_metrics,
                                tab_calculations,
                                tab_embeddings,
                            ) = st.tabs(
                                [
                                    "📥 Ingest Filing & View Chunks",
                                    "📄 Available SEC Filings",
                                    "📈 Financial Observations",
                                    "🧮 Financial Analysis & Calculations",
                                    "🔍 Semantic Search & Embeddings",
                                ]
                            )

                            # Tab 1: Filing Ingestion Workflow (Session 03)
                            with tab_ingest:
                                st.markdown(
                                    "#### Ingest Statutory Filing (10-K / 10-Q)"
                                )
                                st.caption(
                                    "Download primary HTML filing document, extract disclosure sections (Item 1A Risk Factors, Item 7 MD&A), and generate boundary-aware text chunks."
                                )

                                filings_resp = httpx.get(
                                    f"{backend_url}/api/v1/companies/{search_ticker}/filings",
                                    timeout=15.0,
                                )
                                filings_data = (
                                    filings_resp.json()
                                    if filings_resp.status_code == 200
                                    else []
                                )

                                # Filter for supported forms (10-K and 10-Q)
                                eligible_filings = [
                                    f
                                    for f in filings_data
                                    if f.get("form", "").upper()
                                    in ["10-K", "10-Q", "10-K/A", "10-Q/A"]
                                ]

                                if not eligible_filings:
                                    st.info(
                                        "No eligible 10-K or 10-Q filings found for this company."
                                    )
                                else:
                                    filing_options = {
                                        f"{f['form']} ({f['filing_date']}) - Period: {f.get('report_date') or 'N/A'} [Accn: {f['accession_number']}]": f
                                        for f in eligible_filings
                                    }

                                    col_select, col_force = st.columns([3, 1])
                                    with col_select:
                                        selected_label = st.selectbox(
                                            "Select Filing to Ingest",
                                            options=list(filing_options.keys()),
                                            index=0,
                                        )
                                    with col_force:
                                        st.write("")
                                        st.write("")
                                        force_refresh = st.checkbox(
                                            "Force Refresh",
                                            value=False,
                                            help="Re-download and re-parse even if previously ingested.",
                                        )

                                    selected_filing = filing_options[selected_label]
                                    accn = selected_filing["accession_number"]

                                    if st.button(
                                        "⚡ Ingest & Chunk Selected Filing",
                                        type="primary",
                                        use_container_width=True,
                                    ):
                                        with st.spinner(
                                            f"Ingesting filing {accn} for {search_ticker}..."
                                        ):
                                            try:
                                                ingest_url = f"{backend_url}/api/v1/companies/{search_ticker}/filings/{accn}/ingest"
                                                ingest_resp = httpx.post(
                                                    ingest_url,
                                                    params={
                                                        "force_refresh": force_refresh
                                                    },
                                                    timeout=45.0,
                                                )

                                                if ingest_resp.status_code == 200:
                                                    result = ingest_resp.json()
                                                    st.success(
                                                        f"Filing {accn} successfully processed! (Status: {result.get('processing_status')})"
                                                    )

                                                    # Metric summary cards
                                                    mcol1, mcol2, mcol3, mcol4 = (
                                                        st.columns(4)
                                                    )
                                                    with mcol1:
                                                        st.metric(
                                                            "Generated Chunks",
                                                            result.get(
                                                                "total_chunks", 0
                                                            ),
                                                        )
                                                    with mcol2:
                                                        st.metric(
                                                            "Sections Extracted",
                                                            len(
                                                                result.get(
                                                                    "sections_extracted",
                                                                    [],
                                                                )
                                                            ),
                                                        )
                                                    with mcol3:
                                                        st.metric(
                                                            "Document Size",
                                                            f"{result.get('file_size_bytes', 0) / 1024:.1f} KB",
                                                        )
                                                    with mcol4:
                                                        st.metric(
                                                            "Form Type",
                                                            result.get(
                                                                "filing_type", "—"
                                                            ),
                                                        )

                                                    # Section badges
                                                    st.markdown(
                                                        "**Extracted Sections:**"
                                                    )
                                                    sec_badges = " ".join(
                                                        f'<span class="badge-active">✓ {s}</span>'
                                                        for s in result.get(
                                                            "sections_extracted", []
                                                        )
                                                    )
                                                    if result.get("sections_not_found"):
                                                        sec_badges += " " + " ".join(
                                                            f'<span class="badge-offline">✗ {s} (not found)</span>'
                                                            for s in result.get(
                                                                "sections_not_found",
                                                                [],
                                                            )
                                                        )
                                                    st.markdown(
                                                        sec_badges,
                                                        unsafe_allow_html=True,
                                                    )

                                                else:
                                                    st.error(
                                                        f"Ingestion failed ({ingest_resp.status_code}): {ingest_resp.text}"
                                                    )
                                            except httpx.RequestError as exc:
                                                st.error(
                                                    f"Network error during ingestion: {exc}"
                                                )

                                    st.markdown("---")

                                    # Chunk Inspection Section
                                    st.markdown("#### 🔍 Inspect Document Chunks")
                                    chunks_resp = httpx.get(
                                        f"{backend_url}/api/v1/companies/{search_ticker}/documents/{accn}/chunks",
                                        timeout=15.0,
                                    )
                                    if chunks_resp.status_code == 200:
                                        chunks_list = chunks_resp.json()
                                        if chunks_list:
                                            st.caption(
                                                f"Found {len(chunks_list)} stored chunks for filing `{accn}`:"
                                            )

                                            # Section filter for inspection
                                            available_sec_ids = sorted(
                                                {
                                                    c["section_identifier"]
                                                    for c in chunks_list
                                                }
                                            )
                                            selected_sec_filter = st.selectbox(
                                                "Filter Chunks by Section",
                                                options=["All Sections"]
                                                + available_sec_ids,
                                                index=0,
                                            )

                                            filtered_chunks = (
                                                chunks_list
                                                if selected_sec_filter == "All Sections"
                                                else [
                                                    c
                                                    for c in chunks_list
                                                    if c["section_identifier"]
                                                    == selected_sec_filter
                                                ]
                                            )

                                            for chk in filtered_chunks[:15]:
                                                with st.expander(
                                                    f"Chunk #{chk['chunk_index']} — {chk['section_title']} ({chk['char_count']} chars, offset {chk['start_offset']}-{chk['end_offset']})"
                                                ):
                                                    st.markdown(
                                                        f"**Provenance:** `{chk['ticker']}` | Form: `{chk['filing_type']}` | Accession: `{chk['accession_number']}`"
                                                    )
                                                    st.markdown(
                                                        f"**Source SEC Archive:** [View File]({chk['source_url']})"
                                                    )
                                                    st.text_area(
                                                        "Extracted Text Content",
                                                        value=chk["chunk_text"],
                                                        height=180,
                                                        disabled=True,
                                                        key=f"chunk_{chk['chunk_id']}",
                                                    )
                                        else:
                                            st.info(
                                                "Filing has not been ingested yet. Click 'Ingest & Chunk Selected Filing' above."
                                            )

                            # Tab 2: Available SEC Filings
                            with tab_filings:
                                if filings_data:
                                    table_data = [
                                        {
                                            "Form": f.get("form"),
                                            "Filing Date": f.get("filing_date"),
                                            "Report Period": f.get("report_date")
                                            or "—",
                                            "Accession Number": f.get(
                                                "accession_number"
                                            ),
                                            "XBRL": "Yes" if f.get("is_xbrl") else "No",
                                            "SEC Archive": f.get("url") or "—",
                                        }
                                        for f in filings_data[:25]
                                    ]
                                    st.dataframe(table_data, use_container_width=True)
                                else:
                                    st.info("No recent filings found for this company.")

                            # Tab 3: Financial Observations
                            with tab_metrics:
                                fin_resp = httpx.get(
                                    f"{backend_url}/api/v1/companies/{search_ticker}/financials",
                                    timeout=20.0,
                                )
                                if fin_resp.status_code == 200:
                                    observations = fin_resp.json()
                                    if observations:
                                        st.caption(
                                            f"Showing {len(observations)} normalized observations:"
                                        )
                                        obs_data = [
                                            {
                                                "Metric": obs.get("metric_name"),
                                                "Statement": obs.get("statement_type"),
                                                "Value": f"{obs.get('numeric_value', 0):,.2f}",
                                                "Unit": obs.get("unit"),
                                                "Period End": obs.get("period_end"),
                                                "Period Type": obs.get("period_type"),
                                                "Form": obs.get("filing_type"),
                                                "Original XBRL Tag": obs.get(
                                                    "original_tag"
                                                ),
                                            }
                                            for obs in observations[:50]
                                        ]
                                        st.dataframe(obs_data, use_container_width=True)
                                    else:
                                        st.info(
                                            "No financial observations extracted for this company."
                                        )
                                else:
                                    st.warning(
                                        "Could not extract financial observations."
                                    )

                            # Tab 4: Financial Analysis & Deterministic Calculations (Session 04)
                            with tab_calculations:
                                st.markdown(
                                    "#### Deterministic Financial Calculation Engine"
                                )
                                st.caption(
                                    "Computes verified performance indicators, profitability margins, liquidity ratios, "
                                    "and cash flow metrics using pure Python arithmetic with transparent calculation receipts."
                                )

                                c_col1, c_col2, c_col3 = st.columns([1, 1, 2])
                                with c_col1:
                                    selected_period_type = st.selectbox(
                                        "Reporting Scope",
                                        options=["annual", "quarterly"],
                                        index=0,
                                        format_func=lambda x: (
                                            "Annual (10-K)"
                                            if x == "annual"
                                            else "Quarterly (10-Q)"
                                        ),
                                    )
                                with c_col2:
                                    calc_start_year = st.number_input(
                                        "Start Year",
                                        min_value=2015,
                                        max_value=2030,
                                        value=2020,
                                    )
                                with c_col3:
                                    calc_end_year = st.number_input(
                                        "End Year",
                                        min_value=2015,
                                        max_value=2030,
                                        value=2024,
                                    )

                                metric_options = [
                                    "revenue_growth",
                                    "gross_profit_margin",
                                    "operating_profit_margin",
                                    "net_profit_margin",
                                    "current_ratio",
                                    "debt_to_equity_ratio",
                                    "long_term_debt_to_equity",
                                    "return_on_assets",
                                    "return_on_equity",
                                    "operating_cash_flow_margin",
                                    "free_cash_flow",
                                ]
                                selected_metrics = st.multiselect(
                                    "Select Financial Metrics to Compute",
                                    options=metric_options,
                                    default=metric_options,
                                    help="Select one or more canonical metrics to calculate across the specified period range.",
                                )

                                if st.button(
                                    "⚡ Calculate Financial Metrics",
                                    type="primary",
                                    use_container_width=True,
                                ):
                                    with st.spinner(
                                        "Computing deterministic financial metrics..."
                                    ):
                                        try:
                                            calc_resp = httpx.post(
                                                f"{backend_url}/api/v1/companies/{search_ticker}/calculations",
                                                json={
                                                    "start_year": int(calc_start_year),
                                                    "end_year": int(calc_end_year),
                                                    "period_type": selected_period_type,
                                                    "metrics": selected_metrics,
                                                },
                                                timeout=25.0,
                                            )
                                            if calc_resp.status_code == 200:
                                                summary = calc_resp.json()
                                                st.session_state[
                                                    f"calculations_{search_ticker}"
                                                ] = summary
                                                st.success(
                                                    f"Completed calculations for {search_ticker}: "
                                                    f"{summary.get('total_calculated', 0)} calculated, "
                                                    f"{summary.get('total_unavailable', 0)} unavailable, "
                                                    f"{summary.get('total_invalid', 0)} invalid inputs."
                                                )
                                            else:
                                                st.error(
                                                    f"Calculation failed ({calc_resp.status_code}): {calc_resp.text}"
                                                )
                                        except httpx.RequestError as exc:
                                            st.error(
                                                f"Error communicating with backend: {exc}"
                                            )

                                # Display stored/cached calculations
                                current_calcs = st.session_state.get(
                                    f"calculations_{search_ticker}"
                                )
                                if not current_calcs:
                                    # Fetch existing calculations from database
                                    try:
                                        existing_calcs_resp = httpx.get(
                                            f"{backend_url}/api/v1/companies/{search_ticker}/calculations",
                                            params={
                                                "period_type": selected_period_type
                                            },
                                            timeout=15.0,
                                        )
                                        if (
                                            existing_calcs_resp.status_code == 200
                                            and existing_calcs_resp.json()
                                        ):
                                            items = existing_calcs_resp.json()
                                            current_calcs = {
                                                "calculations": items,
                                                "total_calculated": sum(
                                                    1
                                                    for x in items
                                                    if x.get("status") == "calculated"
                                                ),
                                                "total_unavailable": sum(
                                                    1
                                                    for x in items
                                                    if x.get("status") == "unavailable"
                                                ),
                                                "total_invalid": sum(
                                                    1
                                                    for x in items
                                                    if x.get("status")
                                                    == "invalid_inputs"
                                                ),
                                            }
                                    except (httpx.HTTPError, ValueError) as exc:
                                        logger.debug(
                                            "Could not pre-fetch calculations: %s", exc
                                        )

                                if current_calcs and current_calcs.get("calculations"):
                                    all_calcs = current_calcs["calculations"]

                                    # Summary scorecards
                                    m_c1, m_c2, m_c3 = st.columns(3)
                                    with m_c1:
                                        st.metric(
                                            "Metrics Calculated",
                                            current_calcs.get("total_calculated", 0),
                                        )
                                    with m_c2:
                                        st.metric(
                                            "Unavailable Metrics",
                                            current_calcs.get("total_unavailable", 0),
                                        )
                                    with m_c3:
                                        st.metric(
                                            "Invalid Inputs",
                                            current_calcs.get("total_invalid", 0),
                                        )

                                    calculated_list = [
                                        c
                                        for c in all_calcs
                                        if c.get("status") == "calculated"
                                    ]
                                    if calculated_list:
                                        st.markdown("##### Calculated Metrics Summary")
                                        table_rows = []
                                        for c in calculated_list:
                                            val_str = (
                                                f"{c['calculated_value']:,.2f}%"
                                                if c["unit"] == "percentage"
                                                else f"${c['calculated_value']:,.2f}"
                                                if c["unit"] == "USD"
                                                else f"{c['calculated_value']:,.4f}"
                                            )
                                            table_rows.append(
                                                {
                                                    "Period End": c.get("period_end"),
                                                    "Fiscal Period": f"FY{c.get('fiscal_year', '')} {c.get('fiscal_period', '')}".strip(),
                                                    "Metric": c.get("formula_name"),
                                                    "Value": val_str,
                                                    "Unit": c.get("unit"),
                                                    "Formula": c.get(
                                                        "formula_expression"
                                                    ),
                                                }
                                            )
                                        st.dataframe(
                                            table_rows, use_container_width=True
                                        )

                                        # Calculation Receipts Expander
                                        st.markdown(
                                            "##### Verifiable Calculation Receipts"
                                        )
                                        for idx, c in enumerate(calculated_list[:15]):
                                            val_display = (
                                                f"{c['calculated_value']:,.2f}%"
                                                if c["unit"] == "percentage"
                                                else f"${c['calculated_value']:,.2f}"
                                                if c["unit"] == "USD"
                                                else f"{c['calculated_value']:,.4f}"
                                            )
                                            with st.expander(
                                                f"Receipt: {c.get('formula_name')} [{c.get('period_end')}] — {val_display}"
                                            ):
                                                st.markdown(
                                                    f"**Formula**: `{c.get('formula_expression')}`"
                                                )
                                                st.markdown(
                                                    f"**Calculation ID**: `{c.get('calculation_id')}`"
                                                )
                                                st.markdown(
                                                    f"**Executed At**: `{c.get('calculated_at')}`"
                                                )

                                                if c.get("warnings"):
                                                    for w in c["warnings"]:
                                                        st.info(f"ℹ️ {w}")

                                                if c.get("inputs"):
                                                    st.markdown(
                                                        "**Source Input Observations:**"
                                                    )
                                                    inputs_table = [
                                                        {
                                                            "Input Metric": inp.get(
                                                                "metric_name"
                                                            ),
                                                            "Reported Value": f"{inp.get('value', 0):,}",
                                                            "Unit": inp.get("unit"),
                                                            "Period End": inp.get(
                                                                "period_end"
                                                            ),
                                                            "Form": inp.get(
                                                                "filing_type"
                                                            )
                                                            or "—",
                                                            "Accession": inp.get(
                                                                "accession_number"
                                                            )
                                                            or "—",
                                                            "Source Link": inp.get(
                                                                "source_url"
                                                            )
                                                            or "—",
                                                            "Note": inp.get(
                                                                "normalization_note"
                                                            )
                                                            or "—",
                                                        }
                                                        for inp in c["inputs"]
                                                    ]
                                                    st.dataframe(
                                                        inputs_table,
                                                        use_container_width=True,
                                                    )

                                    # Unavailable metrics section
                                    unavailable_list = [
                                        c
                                        for c in all_calcs
                                        if c.get("status") != "calculated"
                                    ]
                                    if unavailable_list:
                                        with st.expander(
                                            f"⚠️ Unavailable or Invalid Metrics ({len(unavailable_list)})"
                                        ):
                                            for un in unavailable_list:
                                                st.markdown(
                                                    f"- **{un.get('formula_name')}** (`{un.get('period_end')}`): "
                                                    f"*{un.get('unavailable_reason')}*"
                                                )

                            # Tab 5: Semantic Search & Embeddings (Session 05)
                            with tab_embeddings:
                                st.markdown(
                                    "#### 🔍 Semantic Embeddings & Persistent Vector Index"
                                )
                                st.caption(
                                    "Generate 384-dimensional dense semantic vector embeddings for document chunks using "
                                    "sentence-transformers/all-MiniLM-L6-v2, and execute semantic similarity search."
                                )

                                # Status diagnostics
                                try:
                                    emb_stat_resp = httpx.get(
                                        f"{backend_url}/api/v1/companies/{search_ticker}/embeddings/status",
                                        timeout=10.0,
                                    )
                                    if emb_stat_resp.status_code == 200:
                                        stat_data = emb_stat_resp.json()
                                        c_avail, c_idx, c_pend, c_fail = st.columns(4)
                                        with c_avail:
                                            st.metric(
                                                "Total Chunks",
                                                stat_data.get(
                                                    "total_available_chunks", 0
                                                ),
                                            )
                                        with c_idx:
                                            st.metric(
                                                "Indexed Chunks",
                                                stat_data.get("indexed_chunks", 0),
                                            )
                                        with c_pend:
                                            st.metric(
                                                "Pending Embeddings",
                                                stat_data.get("pending_chunks", 0),
                                            )
                                        with c_fail:
                                            st.metric(
                                                "Failed Embeddings",
                                                stat_data.get("failed_chunks", 0),
                                            )

                                        st.caption(
                                            f"🤖 Dense Model: `{stat_data.get('active_model')}` | "
                                            f"📐 Dimension: `{stat_data.get('embedding_dimension')}D` | "
                                            f"⚡ Vector Backend: `{stat_data.get('active_vector_backend', '').upper()}`"
                                        )
                                except (httpx.HTTPError, ValueError):
                                    st.warning(
                                        "Could not fetch embedding status from backend."
                                    )

                                # Fetch BM25 status
                                try:
                                    bm25_stat_resp = httpx.get(
                                        f"{backend_url}/api/v1/companies/{search_ticker}/bm25/status",
                                        timeout=10.0,
                                    )
                                    if bm25_stat_resp.status_code == 200:
                                        bm25_data = bm25_stat_resp.json()
                                        st.caption(
                                            f"📚 BM25 Status: `{bm25_data.get('indexed_chunks', 0)}` indexed chunks | "
                                            f"`{bm25_data.get('total_tokens', 0):,}` tokens | "
                                            f"Avg Length: `{bm25_data.get('avg_doc_len', 0)}` tokens/chunk"
                                        )
                                except (httpx.HTTPError, ValueError):
                                    pass

                                st.markdown("---")
                                st.markdown("##### ⚡ Generate / Update Indexes")
                                idx_c1, idx_c2, idx_c3 = st.columns([2, 1, 1])
                                with idx_c1:
                                    force_reindex = st.checkbox(
                                        "Force Re-Index All Chunks",
                                        value=False,
                                        help="Re-index chunks even if content hash is unchanged.",
                                        key=f"force_reindex_{search_ticker}",
                                    )
                                with idx_c2:
                                    trigger_index = st.button(
                                        "⚡ Build Dense Vector Index",
                                        type="primary",
                                        use_container_width=True,
                                        key=f"btn_index_{search_ticker}",
                                    )
                                with idx_c3:
                                    trigger_bm25_index = st.button(
                                        "⚡ Build BM25 Sparse Index",
                                        type="secondary",
                                        use_container_width=True,
                                        key=f"btn_bm25_index_{search_ticker}",
                                    )

                                if trigger_index:
                                    with st.spinner(
                                        f"Generating embeddings and updating vector index for {search_ticker}..."
                                    ):
                                        try:
                                            idx_resp = httpx.post(
                                                f"{backend_url}/api/v1/companies/{search_ticker}/embeddings/index",
                                                params={"force_reindex": force_reindex},
                                                timeout=90.0,
                                            )
                                            if idx_resp.status_code == 200:
                                                res_summary = idx_resp.json()
                                                st.success(
                                                    res_summary.get("message")
                                                    or "Dense indexing completed!"
                                                )
                                                st.rerun()
                                            else:
                                                st.error(
                                                    f"Indexing failed ({idx_resp.status_code}): {idx_resp.text}"
                                                )
                                        except httpx.HTTPError as exc:
                                            st.error(
                                                f"Error communicating with backend: {exc}"
                                            )

                                if trigger_bm25_index:
                                    with st.spinner(
                                        f"Tokenizing and updating BM25 index for {search_ticker}..."
                                    ):
                                        try:
                                            b_resp = httpx.post(
                                                f"{backend_url}/api/v1/companies/{search_ticker}/bm25/index",
                                                params={"force_reindex": force_reindex},
                                                timeout=60.0,
                                            )
                                            if b_resp.status_code == 200:
                                                b_summary = b_resp.json()
                                                st.success(
                                                    b_summary.get("message")
                                                    or "BM25 indexing completed!"
                                                )
                                                st.rerun()
                                            else:
                                                st.error(
                                                    f"BM25 indexing failed ({b_resp.status_code}): {b_resp.text}"
                                                )
                                        except httpx.HTTPError as exc:
                                            st.error(
                                                f"Error communicating with backend: {exc}"
                                            )

                                st.markdown("---")
                                st.markdown("##### 🔎 Dense Semantic Similarity Search")
                                query_text = st.text_input(
                                    "Natural Language Query",
                                    placeholder="e.g. What are the key risk factors affecting international supply chains?",
                                    key=f"query_{search_ticker}",
                                )
                                s_c1, s_c2, s_c3 = st.columns(3)
                                with s_c1:
                                    filter_section = st.selectbox(
                                        "Section Filter",
                                        options=[
                                            "All Sections",
                                            "ITEM_1A",
                                            "ITEM_7",
                                            "ITEM_1",
                                            "ITEM_7A",
                                        ],
                                        index=0,
                                        key=f"filter_sec_{search_ticker}",
                                    )
                                with s_c2:
                                    top_k_val = st.slider(
                                        "Top K",
                                        min_value=1,
                                        max_value=20,
                                        value=5,
                                        key=f"topk_{search_ticker}",
                                    )
                                with s_c3:
                                    sim_thresh = st.slider(
                                        "Similarity Threshold",
                                        min_value=0.0,
                                        max_value=1.0,
                                        value=0.0,
                                        step=0.05,
                                        key=f"thresh_{search_ticker}",
                                    )

                                if st.button(
                                    "🔍 Search Documents",
                                    type="secondary",
                                    key=f"btn_search_{search_ticker}",
                                ):
                                    if not query_text or not query_text.strip():
                                        st.warning("Please enter a search query.")
                                    else:
                                        with st.spinner(
                                            "Searching semantic vector index..."
                                        ):
                                            try:
                                                sec_id = (
                                                    None
                                                    if filter_section == "All Sections"
                                                    else filter_section
                                                )
                                                search_payload = {
                                                    "query": query_text.strip(),
                                                    "ticker": search_ticker,
                                                    "section_identifier": sec_id,
                                                    "top_k": top_k_val,
                                                    "similarity_threshold": sim_thresh,
                                                }
                                                s_resp = httpx.post(
                                                    f"{backend_url}/api/v1/search/semantic",
                                                    json=search_payload,
                                                    timeout=30.0,
                                                )
                                                if s_resp.status_code == 200:
                                                    search_results = s_resp.json()
                                                    if not search_results:
                                                        st.info(
                                                            "No matching chunks found matching criteria."
                                                        )
                                                    else:
                                                        st.markdown(
                                                            f"Found **{len(search_results)}** relevant chunks:"
                                                        )
                                                        for rank, r in enumerate(
                                                            search_results, start=1
                                                        ):
                                                            sim_pct = (
                                                                r["similarity_score"]
                                                                * 100
                                                            )
                                                            with st.expander(
                                                                f"#{rank} | Match: {r['similarity_score']:.4f} ({sim_pct:.1f}%) | "
                                                                f"{r['section_title']} [{r['filing_type']} - {r['accession_number']}]"
                                                            ):
                                                                st.markdown(
                                                                    f"> {r['chunk_text']}"
                                                                )
                                                                st.markdown(
                                                                    f"**Company**: {r['company_name']} (`{r['ticker']}`) | "
                                                                    f"**Filing Date**: {r['filing_date']} | "
                                                                    f"**Period End**: {r.get('report_date') or 'N/A'}"
                                                                )
                                                                st.markdown(
                                                                    f"[📄 View Statutory SEC EDGAR Filing]({r['source_url']})"
                                                                )
                                                else:
                                                    st.error(
                                                        f"Search failed ({s_resp.status_code}): {s_resp.text}"
                                                    )
                                            except httpx.HTTPError as exc:
                                                st.error(f"Search error: {exc}")

                    except httpx.RequestError as exc:
                        st.error(f"Network error querying backend service: {exc}")

    # -------------------------------------------------------------------------
    # View 3: Hybrid Research Search (Session 06)
    # -------------------------------------------------------------------------
    elif nav_selection == "Hybrid Research Search (RRF)":
        st.markdown("### 🔍 Hybrid Financial Research Search")
        st.caption(
            "Combines Dense Semantic Vector Similarity (sentence-transformers) and Sparse BM25 Lexical Search "
            "using Reciprocal Rank Fusion (RRF) for explainable, high-precision retrieval over statutory SEC disclosures."
        )

        # Operational Index Diagnostics
        idx_stat_c1, idx_stat_c2 = st.columns(2)
        with idx_stat_c1:
            try:
                stat_resp = httpx.get(f"{backend_url}/api/v1/index/stats", timeout=5.0)
                if stat_resp.status_code == 200:
                    stats = stat_resp.json()
                    st.markdown(
                        f"""
                        <div class="card">
                            <strong style="color: #00B4D8;">🧠 Dense Vector Index (Session 05)</strong>
                            <div style="margin-top: 0.4rem; color: #F8FAFC; font-size: 0.95rem;">
                                <strong>Vectors:</strong> {stats.get("index_size", 0):,} |
                                <strong>Backend:</strong> {str(stats.get("active_backend", "")).upper()} |
                                <strong>Dim:</strong> {stats.get("embedding_dimension")}D
                            </div>
                            <div style="color: #94A3B8; font-size: 0.8rem; margin-top: 0.2rem;">
                                Model: {str(stats.get("model_name", "")).split("/")[-1]}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            except (httpx.HTTPError, ValueError):
                st.info("Dense vector index stats unavailable.")

        with idx_stat_c2:
            try:
                bm25_stat_resp = httpx.get(
                    f"{backend_url}/api/v1/index/bm25/stats", timeout=5.0
                )
                if bm25_stat_resp.status_code == 200:
                    bstats = bm25_stat_resp.json()
                    st.markdown(
                        f"""
                        <div class="card">
                            <strong style="color: #06D6A0;">📚 BM25 Sparse Index (Session 06)</strong>
                            <div style="margin-top: 0.4rem; color: #F8FAFC; font-size: 0.95rem;">
                                <strong>Indexed Chunks:</strong> {bstats.get("total_chunks", 0):,} |
                                <strong>Vocab:</strong> {bstats.get("vocab_size", 0):,} words
                            </div>
                            <div style="color: #94A3B8; font-size: 0.8rem; margin-top: 0.2rem;">
                                Avg Chunk Length: {bstats.get("avg_doc_len", 0)} tokens | Tokenizer v{bstats.get("tokenizer_version", "1.0.0")}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            except (httpx.HTTPError, ValueError):
                st.info("BM25 sparse index stats unavailable.")

        st.markdown("---")
        st.markdown("#### 🔎 Query Disclosures")

        global_query = st.text_input(
            "Enter a Financial Question, Keyword, or Disclosure Topic",
            placeholder="e.g. What risks affect the company's revenue and operating cash-flow?",
            key="global_hybrid_query",
        )

        col_mode, col_t, col_f, col_s = st.columns(4)
        with col_mode:
            retrieval_mode = st.selectbox(
                "Retrieval Mode",
                options=[
                    "Hybrid (RRF)",
                    "Dense Semantic (Vector)",
                    "Sparse BM25 (Lexical)",
                ],
                index=0,
                help="Hybrid blends vector similarity and keyword search via Reciprocal Rank Fusion.",
            )
        with col_t:
            target_ticker = (
                st.text_input("Ticker Filter (Optional)", placeholder="e.g. AAPL")
                .strip()
                .upper()
            )
        with col_f:
            target_filing = st.selectbox(
                "Filing Form", options=["All Forms", "10-K", "10-Q"], index=0
            )
        with col_s:
            target_sec = st.selectbox(
                "Section Filter",
                options=[
                    "All Sections",
                    "ITEM_1A (Risk Factors)",
                    "ITEM_7 (MD&A)",
                    "ITEM_1 (Business)",
                    "ITEM_7A (Market Risk)",
                ],
                index=0,
            )

        col_k, col_rrf, _ = st.columns([1, 1, 2])
        with col_k:
            global_top_k = st.slider("Top Results", min_value=1, max_value=25, value=5)
        with col_rrf:
            rrf_k = st.slider(
                "RRF Constant (k)",
                min_value=10,
                max_value=100,
                value=60,
                step=5,
                help="Smoothing parameter k in 1 / (k + rank). Standard default: 60.",
                disabled=(retrieval_mode != "Hybrid (RRF)"),
            )

        if st.button("🔍 Execute Search", type="primary", use_container_width=True):
            if not global_query.strip():
                st.warning("Please enter a question or search query.")
            else:
                sec_map = {
                    "ITEM_1A (Risk Factors)": "ITEM_1A",
                    "ITEM_7 (MD&A)": "ITEM_7",
                    "ITEM_1 (Business)": "ITEM_1",
                    "ITEM_7A (Market Risk)": "ITEM_7A",
                }
                sec_code = sec_map.get(target_sec)
                filing_code = None if target_filing == "All Forms" else target_filing

                # -------------------------------------------------------------
                # 1. Hybrid Search Execution
                # -------------------------------------------------------------
                if retrieval_mode == "Hybrid (RRF)":
                    with st.spinner(
                        "Executing hybrid dense-sparse retrieval with RRF..."
                    ):
                        try:
                            payload = {
                                "query": global_query.strip(),
                                "ticker": target_ticker if target_ticker else None,
                                "filing_type": filing_code,
                                "section_identifier": sec_code,
                                "top_k": global_top_k,
                                "rrf_constant": rrf_k,
                                "dense_limit": 50,
                                "sparse_limit": 50,
                            }
                            res = httpx.post(
                                f"{backend_url}/api/v1/search/hybrid",
                                json=payload,
                                timeout=30.0,
                            )
                            if res.status_code == 200:
                                h_data = res.json()
                                items = h_data.get("results", [])
                                diag = h_data.get("diagnostics", {})
                                warnings = h_data.get("warnings", [])

                                for w in warnings:
                                    st.warning(f"⚠️ {w}")

                                if not items:
                                    st.info("No matching document chunks found.")
                                else:
                                    # Diagnostic banner
                                    status_badge = (
                                        '<span class="badge-active">Normal Hybrid</span>'
                                        if h_data.get("status") == "success"
                                        else '<span class="badge-planned">Degraded Mode</span>'
                                    )
                                    st.markdown(
                                        f"""
                                        <div style="background-color: #1C2541; padding: 0.75rem 1rem; border-radius: 8px; margin-bottom: 1rem; border: 1px solid #334155;">
                                            {status_badge} &nbsp;
                                            <strong>Fused Candidates:</strong> {diag.get("total_unique_candidates", 0)} total |
                                            <strong>Dense Pool:</strong> {diag.get("dense_candidates_count", 0)} |
                                            <strong>BM25 Pool:</strong> {diag.get("sparse_candidates_count", 0)} |
                                            <strong>Mutual Overlap:</strong> {diag.get("overlap_candidates_count", 0)} |
                                            <strong>Duration:</strong> {diag.get("total_duration_seconds", 0):.3f}s
                                        </div>
                                        """,
                                        unsafe_allow_html=True,
                                    )

                                    for rank, item in enumerate(items, start=1):
                                        sources = item.get("retrieval_sources", [])
                                        source_tags: list[str] = []
                                        if "dense" in sources:
                                            d_score = item.get("dense_score")
                                            score_str = (
                                                f"{d_score:.4f}"
                                                if d_score is not None
                                                else "N/A"
                                            )
                                            source_tags.append(
                                                f"Dense Rank #{item.get('dense_rank')} (Score: {score_str})"
                                            )
                                        if "sparse" in sources:
                                            b_score = item.get("bm25_score")
                                            score_str = (
                                                f"{b_score:.2f}"
                                                if b_score is not None
                                                else "N/A"
                                            )
                                            source_tags.append(
                                                f"BM25 Rank #{item.get('sparse_rank')} (Score: {score_str})"
                                            )

                                        tag_display = " | ".join(source_tags)
                                        rrf_str = f"{item['rrf_score']:.6f}"

                                        with st.expander(
                                            f"#{rank} | RRF Score: {rrf_str} | {item['ticker']} - {item['section_title']} ({item['filing_type']})"
                                        ):
                                            st.markdown(
                                                f"<span style='color: #00B4D8; font-size: 0.85rem;'>🔍 Sources: {tag_display}</span>",
                                                unsafe_allow_html=True,
                                            )
                                            st.markdown(f"> {item['chunk_text']}")
                                            st.caption(
                                                f"**Company**: {item['company_name']} (`CIK {item['cik']}`) | "
                                                f"**Filing Date**: {item['filing_date']} | "
                                                f"**Accession**: `{item['accession_number']}` | "
                                                f"**Chunk ID**: `{item['chunk_id']}`"
                                            )
                                            st.markdown(
                                                f"[📄 View Statutory SEC EDGAR Filing]({item['source_url']})"
                                            )
                            else:
                                st.error(
                                    f"Search failed ({res.status_code}): {res.text}"
                                )
                        except httpx.HTTPError as exc:
                            st.error(f"Error connecting to backend: {exc}")

                # -------------------------------------------------------------
                # 2. Dense Semantic Search Execution
                # -------------------------------------------------------------
                elif retrieval_mode == "Dense Semantic (Vector)":
                    with st.spinner("Executing dense vector similarity search..."):
                        try:
                            payload = {
                                "query": global_query.strip(),
                                "ticker": target_ticker if target_ticker else None,
                                "filing_type": filing_code,
                                "section_identifier": sec_code,
                                "top_k": global_top_k,
                                "similarity_threshold": 0.0,
                            }
                            res = httpx.post(
                                f"{backend_url}/api/v1/search/semantic",
                                json=payload,
                                timeout=30.0,
                            )
                            if res.status_code == 200:
                                items = res.json()
                                if not items:
                                    st.info("No matching document chunks found.")
                                else:
                                    st.success(
                                        f"Retrieved {len(items)} relevant chunks:"
                                    )
                                    for rank, item in enumerate(items, start=1):
                                        score_pct = item["similarity_score"] * 100
                                        with st.expander(
                                            f"#{rank} | Cosine Match: {item['similarity_score']:.4f} ({score_pct:.1f}%) | "
                                            f"{item['ticker']} - {item['section_title']} ({item['filing_type']})"
                                        ):
                                            st.markdown(f"> {item['chunk_text']}")
                                            st.caption(
                                                f"**Company**: {item['company_name']} (`CIK {item['cik']}`) | "
                                                f"**Filing Date**: {item['filing_date']} | "
                                                f"**Accession**: `{item['accession_number']}`"
                                            )
                                            st.markdown(
                                                f"[📄 View SEC EDGAR Source]({item['source_url']})"
                                            )
                            else:
                                st.error(
                                    f"Search failed ({res.status_code}): {res.text}"
                                )
                        except httpx.HTTPError as exc:
                            st.error(f"Error connecting to backend: {exc}")

                # -------------------------------------------------------------
                # 3. Sparse BM25 Search Execution
                # -------------------------------------------------------------
                elif retrieval_mode == "Sparse BM25 (Lexical)":
                    with st.spinner("Executing BM25 lexical keyword search..."):
                        try:
                            payload = {
                                "query": global_query.strip(),
                                "ticker": target_ticker if target_ticker else None,
                                "filing_type": filing_code,
                                "section_identifier": sec_code,
                                "top_k": global_top_k,
                            }
                            res = httpx.post(
                                f"{backend_url}/api/v1/search/sparse",
                                json=payload,
                                timeout=30.0,
                            )
                            if res.status_code == 200:
                                items = res.json()
                                if not items:
                                    st.info(
                                        "No matching document chunks found with query keywords."
                                    )
                                else:
                                    st.success(
                                        f"Retrieved {len(items)} lexical matches:"
                                    )
                                    for rank, item in enumerate(items, start=1):
                                        matched = item.get("matched_terms", [])
                                        matched_str = (
                                            ", ".join(f"`{m}`" for m in matched)
                                            if matched
                                            else "N/A"
                                        )
                                        with st.expander(
                                            f"#{rank} | BM25 Score: {item['bm25_score']:.2f} | "
                                            f"{item['ticker']} - {item['section_title']} ({item['filing_type']})"
                                        ):
                                            st.markdown(
                                                f"**Matched Terms:** {matched_str}"
                                            )
                                            st.markdown(f"> {item['chunk_text']}")
                                            st.caption(
                                                f"**Company**: {item['company_name']} (`CIK {item['cik']}`) | "
                                                f"**Filing Date**: {item['filing_date']} | "
                                                f"**Accession**: `{item['accession_number']}`"
                                            )
                                            st.markdown(
                                                f"[📄 View SEC EDGAR Source]({item['source_url']})"
                                            )
                            else:
                                st.error(
                                    f"Search failed ({res.status_code}): {res.text}"
                                )
                        except httpx.HTTPError as exc:
                            st.error(f"Error connecting to backend: {exc}")

    # -------------------------------------------------------------------------
    # View 4: Financial Research Assistant (Session 08 Grounded RAG)
    # -------------------------------------------------------------------------
    elif nav_selection == "Financial Research Assistant":
        st.markdown("### 🤖 Financial Research Assistant — Evidence-Grounded RAG")
        st.caption(
            "Synthesize objective, evidence-backed answers to corporate finance questions "
            "strictly grounded in statutory SEC EDGAR filings and deterministic calculation receipts."
        )

        # Provider Diagnostics banner
        llm_status = None
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(f"{backend_url}/api/v1/llm/status")
                if res.status_code == 200:
                    llm_status = res.json()
        except Exception:
            pass

        if llm_status:
            is_online = llm_status.get("online", False)
            badge_class = "badge-active" if is_online else "badge-offline"
            st.markdown(
                f'<span class="{badge_class}">● Provider: {llm_status.get("provider")} ({llm_status.get("model")}) — {"ONLINE" if is_online else "OFFLINE"}</span>',
                unsafe_allow_html=True,
            )
            if not is_online and llm_status.get("provider") == "ollama":
                st.warning(
                    f"⚠️ Ollama is not detected at `{llm_status.get('base_url')}`. "
                    f"To enable local LLM generation, start Ollama (`ollama serve`) and pull `{llm_status.get('model')}`. "
                    "Alternatively, test the pipeline with `LLM_PROVIDER=mock`."
                )
        st.write("")

        # Query Formulation
        st.markdown("#### 📝 Financial Research Inquiry")
        research_question = st.text_area(
            "Research Question",
            value="What are the key risk factors and operating margin trends reported by Apple?",
            help="Enter a corporate finance or statutory disclosure question.",
            height=100,
        )

        col_q1, col_q2, col_q3, col_q4 = st.columns([1.5, 1.2, 1.5, 1.5])
        with col_q1:
            q_ticker = (
                st.text_input(
                    "Target Ticker",
                    value="AAPL",
                    help="Company ticker symbol (e.g. AAPL)",
                )
                .strip()
                .upper()
            )
        with col_q2:
            q_filing = st.selectbox(
                "Filing Type", options=["All", "10-K", "10-Q"], index=0
            )
        with col_q3:
            q_section = st.selectbox(
                "Filing Section",
                options=[
                    "All",
                    "ITEM_1A (Risk Factors)",
                    "ITEM_7 (MD&A)",
                    "ITEM_1 (Business)",
                    "ITEM_7A (Market Risk)",
                ],
                index=0,
            )
        with col_q4:
            q_style = st.selectbox(
                "Response Depth",
                options=["detailed", "concise", "bullet_points"],
                index=0,
            )

        with st.expander("⚙️ Advanced RAG & Retrieval Settings", expanded=False):
            col_s1, col_s2, col_s3 = st.columns(3)
            with col_s1:
                top_k = st.slider(
                    "Evidence Passages (Top-K)", min_value=1, max_value=15, value=5
                )
            with col_s2:
                use_reranker = st.checkbox(
                    "Cross-Encoder Reranker",
                    value=True,
                    help="Rerank candidates using cross-encoder model",
                )
            with col_s3:
                include_calcs = st.checkbox(
                    "Include Calculation Receipts",
                    value=True,
                    help="Inject relevant deterministic XBRL ratio/margin receipts",
                )

        ask_submitted = st.button(
            "🚀 Synthesize Grounded Research Answer",
            type="primary",
            use_container_width=True,
        )

        if ask_submitted:
            if not research_question.strip():
                st.error("Please enter a research question.")
            else:
                sec_filter = None if q_section == "All" else q_section.split(" ")[0]
                filing_filter = None if q_filing == "All" else q_filing
                payload = {
                    "question": research_question.strip(),
                    "ticker": q_ticker if q_ticker else None,
                    "filing_type": filing_filter,
                    "section_identifier": sec_filter,
                    "top_k": top_k,
                    "use_reranker": use_reranker,
                    "include_calculations": include_calcs,
                    "response_style": q_style,
                }

                with st.spinner(
                    "Executing hybrid retrieval, reranking, and evidence-grounded synthesis..."
                ):
                    try:
                        with httpx.Client(timeout=120.0) as client:
                            resp = client.post(
                                f"{backend_url}/api/v1/research/ask", json=payload
                            )
                            if resp.status_code == 200:
                                ans_data = resp.json()
                                st.session_state["last_rag_answer"] = ans_data
                            else:
                                st.error(f"Error {resp.status_code}: {resp.text}")
                    except Exception as exc:
                        st.error(f"Failed to communicate with RAG endpoint: {exc}")

        # Display answer if present in session state
        ans = st.session_state.get("last_rag_answer")
        if ans:
            st.markdown("---")
            st.markdown("### 📋 Grounded Research Answer")

            status_val = ans.get("answer_status", "unknown")
            status_badges = {
                "answered": '<span class="badge-active">✅ Answered & Verified</span>',
                "verified": '<span class="badge-active">✅ Answered & Verified</span>',
                "partially_supported": '<span style="color: #F59E0B; background-color: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.4); padding: 0.25rem 0.65rem; border-radius: 6px; font-weight: 600;">⚠️ Partially Supported</span>',
                "partially_verified": '<span style="color: #F59E0B; background-color: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.4); padding: 0.25rem 0.65rem; border-radius: 6px; font-weight: 600;">⚠️ Partially Verified</span>',
                "insufficient_evidence": '<span style="color: #38BDF8; background-color: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.4); padding: 0.25rem 0.65rem; border-radius: 6px; font-weight: 600;">ℹ️ Insufficient Evidence</span>',
                "verification_rejected": '<span style="color: #EF4444; background-color: rgba(239, 68, 68, 0.2); border: 1px solid #EF4444; padding: 0.25rem 0.65rem; border-radius: 6px; font-weight: 700;">🚨 Verification Rejected</span>',
                "provider_unavailable": '<span class="badge-offline">🔴 LLM Provider Offline</span>',
                "citation_validation_failed": '<span class="badge-offline">❌ Citation Validation Failed</span>',
                "generation_failed": '<span class="badge-offline">❌ Generation Failed</span>',
            }
            badge_html = status_badges.get(status_val, f"<span>{status_val}</span>")

            m_col1, m_col2, m_col3, m_col4 = st.columns([1.5, 1.5, 1.5, 1.5])
            with m_col1:
                st.markdown(f"**Status:** {badge_html}", unsafe_allow_html=True)
            with m_col2:
                st.markdown(
                    f"**Model:** `{ans.get('provider')}` / `{ans.get('model_name')}`"
                )
            with m_col3:
                st.markdown(f"**Pipeline:** `{ans.get('retrieval_method')}`")
            with m_col4:
                lat = ans.get("generation_metadata", {}).get("latency_ms")
                st.markdown(
                    f"**Latency:** `{lat:,.1f} ms`" if lat else "**Latency:** N/A"
                )

            # Main Answer Text Box
            st.markdown(
                f"""
                <div class="card" style="font-size: 1.05rem; line-height: 1.6; margin-top: 1rem; border-left: 4px solid var(--accent-teal);">
                    {ans.get("answer")}
                </div>
                """,
                unsafe_allow_html=True,
            )

            # -------------------------------------------------------------
            # Session 09: Claim-Level Verification & Anti-Hallucination Audit
            # -------------------------------------------------------------
            v_run_data = None
            ans_id = ans.get("answer_id")
            if ans_id:
                try:
                    v_resp = httpx.get(
                        f"{backend_url}/api/v1/research/answers/{ans_id}/verification",
                        timeout=5.0,
                    )
                    if v_resp.status_code == 200:
                        v_run_data = v_resp.json()
                except Exception:
                    pass

            v_title = "🛡️ Claim-Level Anti-Hallucination Audit"
            if v_run_data:
                ov_status = v_run_data.get("overall_status", "unknown")
                status_icon = {
                    "verified": "✅ VERIFIED",
                    "verified_with_warnings": "⚠️ VERIFIED WITH WARNINGS",
                    "partially_verified": "⚠️ PARTIALLY VERIFIED",
                    "rejected": "🚨 REJECTED (Contradictions / Unsupported Claims)",
                    "inconclusive": "❓ INCONCLUSIVE",
                }.get(ov_status, ov_status.upper())
                v_title = f"🛡️ Claim-Level Anti-Hallucination Audit — {status_icon}"

            with st.expander(v_title, expanded=True if v_run_data else False):
                if not v_run_data:
                    st.info(
                        "No claim verification audit available for this answer yet."
                    )
                    if ans_id and st.button(
                        "🔍 Run Claim-Level Verification", key="btn_run_verif"
                    ):
                        with st.spinner(
                            "Auditing factual claims against SEC evidence..."
                        ):
                            try:
                                vr = httpx.post(
                                    f"{backend_url}/api/v1/research/answers/{ans_id}/verify",
                                    timeout=10.0,
                                )
                                if vr.status_code == 200:
                                    st.success("Verification audit complete!")
                                    st.rerun()
                                else:
                                    st.error(f"Verification failed: {vr.text}")
                            except Exception as ex:
                                st.error(f"Error: {ex}")
                else:
                    # Summary metric cards
                    c_col1, c_col2, c_col3, c_col4, c_col5 = st.columns(5)
                    c_col1.metric("Total Claims", v_run_data.get("total_claims", 0))
                    c_col2.metric("Supported", v_run_data.get("supported_claims", 0))
                    c_col3.metric(
                        "Partially Supported",
                        v_run_data.get("partially_supported_claims", 0),
                    )
                    c_col4.metric(
                        "Unsupported", v_run_data.get("unsupported_claims", 0)
                    )
                    c_col5.metric(
                        "Contradicted", v_run_data.get("contradicted_claims", 0)
                    )

                    # Mismatches or Contradictions banner if any
                    contradictions = v_run_data.get("contradictions", [])
                    num_mismatches = v_run_data.get("numeric_mismatches", [])
                    per_mismatches = v_run_data.get("period_mismatches", [])

                    if contradictions:
                        st.error(
                            f"🚨 **{len(contradictions)} Contradiction(s) Detected:**"
                        )
                        for cd in contradictions:
                            st.markdown(
                                f"- **{cd.get('contradiction_type', '').upper()}**: {cd.get('explanation')}"
                            )

                    if num_mismatches:
                        st.warning(
                            f"🔢 **{len(num_mismatches)} Numeric Discrepancy(ies):**"
                        )
                        for nm in num_mismatches:
                            st.markdown(
                                f"- Claimed `{nm.get('claimed_value')}` vs Evidence `{nm.get('evidence_value')}`: {nm.get('discrepancy_explanation')}"
                            )

                    if per_mismatches:
                        st.warning(f"📅 **{len(per_mismatches)} Period Mismatch(es):**")
                        for pm in per_mismatches:
                            st.markdown(
                                f"- Claimed `{pm.get('claimed_period')}` vs Evidence `{pm.get('evidence_period')}`: {pm.get('mismatch_explanation')}"
                            )

                    st.markdown("##### 📝 Evaluated Claims")
                    claim_results = v_run_data.get("claim_results", [])
                    outcome_badges = {
                        "supported": '<span class="badge-active">✅ Supported</span>',
                        "partially_supported": '<span style="color: #F59E0B; background-color: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.4); padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.8rem; font-weight: 600;">⚠️ Partially Supported</span>',
                        "unsupported": '<span class="badge-offline">❌ Unsupported</span>',
                        "contradicted": '<span style="color: #EF4444; background-color: rgba(239, 68, 68, 0.2); border: 1px solid #EF4444; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.8rem; font-weight: 700;">🚨 Contradicted</span>',
                        "not_verifiable": '<span style="color: #94A3B8; background-color: rgba(148, 163, 184, 0.15); border: 1px solid rgba(148, 163, 184, 0.4); padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.8rem;">❓ Not Verifiable</span>',
                    }
                    for cr in claim_results:
                        c_outcome = cr.get("outcome", "unknown")
                        obadge = outcome_badges.get(
                            c_outcome, f"<span>{c_outcome}</span>"
                        )
                        sup_ids = (
                            ", ".join(cr.get("supporting_evidence_ids", [])) or "None"
                        )
                        conf = cr.get("confidence_score", 0.0)
                        method = cr.get("verification_method", "deterministic")
                        st.markdown(
                            f"""
                            <div style="background-color: #1E293B; border-left: 4px solid {"#10B981" if c_outcome == "supported" else "#EF4444" if c_outcome in ("unsupported", "contradicted") else "#F59E0B"}; border-radius: 6px; padding: 0.75rem 1rem; margin-bottom: 0.6rem;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                                    <span style="font-weight: 600; color: #F8FAFC; font-size: 0.95rem;">{cr.get("claim_text")}</span>
                                    <div>{obadge}</div>
                                </div>
                                <div style="font-size: 0.82rem; color: #94A3B8; margin-top: 0.25rem;">
                                    <strong>Evidence:</strong> <code>{sup_ids}</code> | <strong>Method:</strong> <code>{method}</code> | <strong>Confidence:</strong> <code>{conf:.2f}</code> (heuristic)
                                </div>
                                <div style="font-size: 0.85rem; color: #CBD5E1; margin-top: 0.35rem; font-style: italic;">
                                    {cr.get("verification_reason")}
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

            # Warnings if any
            warnings = ans.get("warnings", [])
            if warnings:
                with st.expander(f"⚠️ Audit Warnings ({len(warnings)})", expanded=False):
                    for w in warnings:
                        st.markdown(f"- {w}")

            # Citations Breakdown
            citations = ans.get("citations", [])
            with st.expander(
                f"📑 Verified Citations ({len(citations)})", expanded=bool(citations)
            ):
                if not citations:
                    st.caption("No statutory citations attached to this response.")
                else:
                    for cit in citations:
                        c_id = cit.get("citation_id")
                        c_type = cit.get("evidence_type")
                        c_ref = cit.get("source_reference")
                        c_url = cit.get("source_url")
                        c_exc = cit.get("excerpt")

                        type_tag = (
                            "📄 SEC Filing Passage"
                            if c_type == "filing_passage"
                            else "🔢 Calculation Receipt"
                        )
                        st.markdown(
                            f"""
                            <div style="background-color: #1E293B; border: 1px solid #334155; border-radius: 8px; padding: 0.85rem; margin-bottom: 0.75rem;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                                    <span style="font-weight: 700; color: #38BDF8; font-size: 0.95rem;">[{c_id}] {c_ref}</span>
                                    <span style="font-size: 0.8rem; color: #94A3B8;">{type_tag}</span>
                                </div>
                                <div style="color: #CBD5E1; font-size: 0.9rem; font-style: italic; margin-bottom: 0.5rem;">
                                    "{c_exc}"
                                </div>
                                <div>
                                    <a href="{c_url}" target="_blank" style="color: #00B4D8; text-decoration: underline; font-size: 0.82rem;">🔗 View Statutory Source on SEC EDGAR</a>
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

            # Retrieved Evidence Passages
            retrieved_ev = ans.get("retrieved_evidence", [])
            with st.expander(
                f"📚 Retrieved Filing Passages ({len(retrieved_ev)})", expanded=False
            ):
                if not retrieved_ev:
                    st.caption("No filing passages retrieved.")
                else:
                    for rev in retrieved_ev:
                        st.markdown(
                            f"**[{rev.get('evidence_id')}]** `{rev.get('ticker')}` {rev.get('filing_type')} ({rev.get('filing_date')}) - {rev.get('section_title') or rev.get('section_identifier')}"
                        )
                        st.caption(
                            f"Dense: {rev.get('dense_score', 0.0):.4f} | BM25: {rev.get('bm25_score', 0.0):.2f} | RRF: {rev.get('rrf_score', 0.0):.5f} | Reranker: {rev.get('reranker_score', 0.0):.4f}"
                        )
                        st.markdown(
                            f"""<div style="background-color: #0F172A; border-left: 3px solid #38BDF8; padding: 0.6rem; margin-bottom: 0.8rem; font-size: 0.88rem; color: #E2E8F0;">
                            {rev.get("chunk_text", "")[:400]}...
                            </div>""",
                            unsafe_allow_html=True,
                        )

            # Calculation Receipts
            calc_ev = ans.get("calculation_evidence", [])
            with st.expander(
                f"🔢 Deterministic Calculation Receipts ({len(calc_ev)})",
                expanded=False,
            ):
                if not calc_ev:
                    st.caption("No deterministic calculation receipts attached.")
                else:
                    for cev in calc_ev:
                        st.markdown(
                            f"**[{cev.get('evidence_id')}]** `{cev.get('metric_name')}`: **{cev.get('calculated_value'):,.2f} {cev.get('unit')}** (Period: `{cev.get('period_end')}`)"
                        )
                        st.caption(
                            f"Formula: `{cev.get('formula')}` | Receipt ID: `{cev.get('calculation_id')}`"
                        )

    # -------------------------------------------------------------------------
    # View 4: Retrieval Evaluation & Evidence Quality (Session 07)
    # -------------------------------------------------------------------------
    elif nav_selection == "Retrieval Evaluation & Evidence Quality":
        st.markdown("### ⚖️ Retrieval Evaluation & Evidence Quality Workspace")
        st.caption(
            "Quantitative Information Retrieval metrics, cross-encoder reranking latency benchmarks, "
            "and deterministic evidence provenance validation."
        )

        st.info(
            "ℹ️ **Evaluation Note**: Ground-truth datasets contain synthetic relevance fixtures for "
            "verifying IR metrics (Precision, Recall, MRR, MAP, NDCG). Synthetic benchmark scores measure "
            "algorithmic mechanics and rank shifts, not human-curated domain expert efficacy."
        )

        tab_comp, tab_query, tab_rerank, tab_evidence = st.tabs(
            [
                "📊 Retrieval Comparison",
                "🔍 Per-Query Inspector",
                "⚡ Reranker Benchmark",
                "🛡️ Evidence Quality Validator",
            ]
        )

        # --- Tab 1: Retrieval Comparison ---
        with tab_comp:
            st.markdown(
                "#### Comparative Benchmark (Dense vs. Sparse vs. Hybrid vs. Reranked)"
            )
            st.caption(
                "Fair comparison over identical evaluation queries, filters, and rank cutoffs."
            )

            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                eval_top_k = st.slider(
                    "Evaluation Cutoff (Top-K)",
                    min_value=1,
                    max_value=20,
                    value=5,
                    step=1,
                )
            with c2:
                include_rerank = st.checkbox(
                    "Include Cross-Encoder Reranker", value=True
                )
            with c3:
                eval_ticker = st.text_input(
                    "Ticker Filter (Optional)", value="", placeholder="e.g. AAPL"
                )

            run_benchmark = st.button("🚀 Run Comparative Benchmark", type="primary")

            if run_benchmark or "last_comparison" in st.session_state:
                if run_benchmark:
                    with st.spinner(
                        "Executing comparative multi-retriever benchmark..."
                    ):
                        try:
                            payload = {
                                "top_k": eval_top_k,
                                "include_reranking": include_rerank,
                                "ticker_filter": eval_ticker.strip().upper()
                                if eval_ticker.strip()
                                else None,
                            }
                            resp = httpx.post(
                                f"{backend_url}/api/v1/evaluation/retrieval/compare",
                                json=payload,
                                timeout=60.0,
                            )
                            if resp.status_code == 200:
                                st.session_state["last_comparison"] = resp.json()
                            else:
                                st.error(
                                    f"Benchmark error ({resp.status_code}): {resp.text}"
                                )
                        except Exception as exc:
                            st.error(f"Failed to connect to backend: {exc}")

                comp_data = st.session_state.get("last_comparison")
                if comp_data:
                    st.success(
                        f"Benchmark completed in {comp_data.get('duration_seconds', 0.0):.2f}s "
                        f"across {comp_data.get('total_queries', 0)} queries (Top-{comp_data.get('top_k', 5)})."
                    )

                    summaries = comp_data.get("method_summaries", {})
                    if summaries:
                        table_rows = []
                        for method_name, m in summaries.items():
                            table_rows.append(
                                {
                                    "Retriever Method": method_name.upper().replace(
                                        "_", " "
                                    ),
                                    "Precision@K": f"{m.get('precision_at_k', 0.0):.4f}",
                                    "Recall@K": f"{m.get('recall_at_k', 0.0):.4f}",
                                    "MRR": f"{m.get('mrr', 0.0):.4f}",
                                    "MAP": f"{m.get('map_score', 0.0):.4f}",
                                    "NDCG@K": f"{m.get('ndcg_at_k', 0.0):.4f}",
                                    "Coverage": f"{m.get('coverage', 0.0) * 100:.1f}%",
                                    "Avg Latency (ms)": f"{m.get('avg_latency_ms', 0.0):.1f} ms",
                                }
                            )
                        st.table(table_rows)

                        # Delta Callouts
                        d_col1, d_col2, d_col3 = st.columns(3)
                        delta_den = comp_data.get("hybrid_delta_vs_dense", {})
                        delta_spa = comp_data.get("hybrid_delta_vs_sparse", {})
                        delta_rr = comp_data.get("reranked_delta_vs_hybrid", {})

                        with d_col1:
                            st.markdown(
                                f"""
                                <div class="card">
                                    <div class="metric-label">Hybrid vs. Dense Baseline</div>
                                    <div class="metric-value">{delta_den.get("ndcg_delta_pct", 0.0):+.1f}%</div>
                                    <p style="color: #94A3B8; font-size: 0.85rem; margin-top: 0.3rem;">
                                        NDCG shift: {delta_den.get("ndcg_delta_pct", 0.0):+.1f}% | Recall: {delta_den.get("recall_delta_pct", 0.0):+.1f}%
                                    </p>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )
                        with d_col2:
                            st.markdown(
                                f"""
                                <div class="card">
                                    <div class="metric-label">Hybrid vs. Sparse BM25</div>
                                    <div class="metric-value">{delta_spa.get("ndcg_delta_pct", 0.0):+.1f}%</div>
                                    <p style="color: #94A3B8; font-size: 0.85rem; margin-top: 0.3rem;">
                                        NDCG shift: {delta_spa.get("ndcg_delta_pct", 0.0):+.1f}% | Recall: {delta_spa.get("recall_delta_pct", 0.0):+.1f}%
                                    </p>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )
                        with d_col3:
                            if delta_rr:
                                st.markdown(
                                    f"""
                                    <div class="card">
                                        <div class="metric-label">Reranked vs. Hybrid</div>
                                        <div class="metric-value">{delta_rr.get("ndcg_delta_pct", 0.0):+.1f}%</div>
                                        <p style="color: #94A3B8; font-size: 0.85rem; margin-top: 0.3rem;">
                                            NDCG shift: {delta_rr.get("ndcg_delta_pct", 0.0):+.1f}% | MRR: {delta_rr.get("mrr_delta_pct", 0.0):+.1f}%
                                        </p>
                                    </div>
                                    """,
                                    unsafe_allow_html=True,
                                )
                            else:
                                st.markdown(
                                    """
                                    <div class="card">
                                        <div class="metric-label">Reranker Status</div>
                                        <div class="metric-value">Not Evaluated</div>
                                        <p style="color: #94A3B8; font-size: 0.85rem; margin-top: 0.3rem;">
                                            Reranking was disabled or unavailable for this run.
                                        </p>
                                    </div>
                                    """,
                                    unsafe_allow_html=True,
                                )

        # --- Tab 2: Per-Query Inspector ---
        with tab_query:
            st.markdown("#### Per-Query Breakdown & Retrieval Positions")
            st.caption(
                "Inspect how individual queries perform across candidate selection and rank fusion."
            )

            comp_data = st.session_state.get("last_comparison")
            if comp_data and "per_query_comparisons" in comp_data:
                pq_list = comp_data["per_query_comparisons"]
                query_labels = [
                    f"{q['query_id']} — {q['query'][:60]}..." for q in pq_list
                ]
                sel_idx = st.selectbox(
                    "Select Query to Inspect",
                    range(len(query_labels)),
                    format_func=lambda i: query_labels[i],
                )

                sel_q = pq_list[sel_idx]
                st.markdown(
                    f"**Query ID**: `{sel_q['query_id']}` | **Ticker**: `{sel_q.get('ticker') or 'Global'}` | **Section**: `{sel_q.get('section') or 'All'}`"
                )
                st.markdown(f'> *"{sel_q["query"]}"*')

                qcol1, qcol2, qcol3, qcol4 = st.columns(4)
                with qcol1:
                    st.metric(
                        "Dense Precision@K", f"{sel_q.get('dense_precision', 0.0):.2f}"
                    )
                with qcol2:
                    st.metric(
                        "Sparse Precision@K",
                        f"{sel_q.get('sparse_precision', 0.0):.2f}",
                    )
                with qcol3:
                    st.metric(
                        "Hybrid Precision@K",
                        f"{sel_q.get('hybrid_precision', 0.0):.2f}",
                    )
                with qcol4:
                    st.metric("Hybrid NDCG@K", f"{sel_q.get('hybrid_ndcg', 0.0):.2f}")

                st.markdown("**Per-Query Comparison Data:**")
                st.json(sel_q)
            else:
                st.info(
                    "Run the Comparative Benchmark in Tab 1 first to populate per-query metrics."
                )

        # --- Tab 3: Reranker Benchmark ---
        with tab_rerank:
            st.markdown("#### Cross-Encoder Reranker Status & Latency Benchmark")
            st.caption("Evaluates CPU inference latency and model configuration.")

            try:
                r_status_resp = httpx.get(
                    f"{backend_url}/api/v1/retrieval/reranker/status", timeout=5.0
                )
                if r_status_resp.status_code == 200:
                    r_status = r_status_resp.json()
                    r1, r2, r3, r4 = st.columns(4)
                    with r1:
                        st.metric("Enabled", "Yes" if r_status.get("enabled") else "No")
                    with r2:
                        st.metric(
                            "Initialized",
                            "Yes" if r_status.get("initialized") else "No (Lazy)",
                        )
                    with r3:
                        st.metric(
                            "Compute Device", r_status.get("device", "cpu").upper()
                        )
                    with r4:
                        st.metric("Batch Size", str(r_status.get("batch_size", 16)))

                    st.markdown(f"**Configured Model**: `{r_status.get('model_name')}`")
                    st.markdown(
                        f"**Status Message**: {r_status.get('message', 'Ready')}"
                    )
                else:
                    st.warning("Could not fetch reranker status from backend.")
            except Exception as exc:
                st.warning(f"Backend offline: {exc}")

            st.markdown("---")
            st.markdown("##### Candidate Over-Fetch & Scoring Mechanics")
            st.markdown(
                """
                - **Candidate Pool**: Hybrid RRF retrieves top 25-50 candidates from combined dense and sparse lists.
                - **Pair Scoring**: `[(query, candidate_chunk_text), ...]` pairs are scored in mini-batches.
                - **Rank Refinement**: Candidates are sorted descending by cross-encoder score; top-K are returned.
                - **Provenance Preservation**: Original RRF scores, dense ranks, and sparse ranks are retained.
                """
            )

        # --- Tab 4: Evidence Quality Validator ---
        with tab_evidence:
            st.markdown("#### Deterministic Evidence Quality & Source Audit")
            st.caption(
                "Validates statutory provenance completeness, SEC archive domains, duplicate passages, and reporting periods."
            )

            e_mode = st.radio(
                "Audit Input Mode",
                ["Test by Natural Language Query", "Test by Chunk IDs"],
                horizontal=True,
            )

            if e_mode == "Test by Natural Language Query":
                ev_query = st.text_input(
                    "Search Query to Retrieve & Audit",
                    value="What are Apple's principal supply chain and single source component risks?",
                )
                ev_method = st.selectbox(
                    "Retriever Method", ["hybrid", "dense", "sparse"]
                )
                ev_top_k = st.slider("Candidates to Audit", 1, 15, 5)

                if st.button("🛡️ Audit Evidence Set", type="primary"):
                    with st.spinner(
                        "Retrieving candidates and auditing evidence provenance..."
                    ):
                        try:
                            ev_payload = {
                                "query": ev_query,
                                "retrieval_method": ev_method,
                                "top_k": ev_top_k,
                            }
                            ev_resp = httpx.post(
                                f"{backend_url}/api/v1/evaluation/evidence/validate",
                                json=ev_payload,
                                timeout=30.0,
                            )
                            if ev_resp.status_code == 200:
                                st.session_state["last_evidence_val"] = ev_resp.json()
                            else:
                                st.error(
                                    f"Validation error ({ev_resp.status_code}): {ev_resp.text}"
                                )
                        except Exception as exc:
                            st.error(f"Failed to connect to backend: {exc}")

            else:
                chunk_ids_raw = st.text_area(
                    "Enter Chunk IDs (one per line)",
                    value="0000320193_000032019323000106_ITEM_1A_0001\n0000320193_000032019323000106_ITEM_1A_0002",
                )
                if st.button("🛡️ Audit Chunk IDs", type="primary"):
                    c_ids = [
                        line.strip()
                        for line in chunk_ids_raw.splitlines()
                        if line.strip()
                    ]
                    with st.spinner("Auditing chunk IDs against document storage..."):
                        try:
                            ev_payload = {"chunk_ids": c_ids}
                            ev_resp = httpx.post(
                                f"{backend_url}/api/v1/evaluation/evidence/validate",
                                json=ev_payload,
                                timeout=30.0,
                            )
                            if ev_resp.status_code == 200:
                                st.session_state["last_evidence_val"] = ev_resp.json()
                            else:
                                st.error(f"Validation error: {ev_resp.text}")
                        except Exception as exc:
                            st.error(f"Backend error: {exc}")

            ev_val_data = st.session_state.get("last_evidence_val")
            if ev_val_data:
                st.markdown("---")
                st.markdown("##### Evidence Audit Summary")

                v1, v2, v3, v4 = st.columns(4)
                with v1:
                    overall = ev_val_data.get("overall_status", "valid").upper()
                    st.metric("Audit Status", overall)
                with v2:
                    st.metric(
                        "Total Inspected",
                        str(ev_val_data.get("total_chunks_inspected", 0)),
                    )
                with v3:
                    st.metric("Fully Valid", str(ev_val_data.get("valid_count", 0)))
                with v4:
                    st.metric(
                        "Warnings Raised", str(ev_val_data.get("warning_count", 0))
                    )

                # Notes and Temporal alerts
                notes = ev_val_data.get("summary_notes", [])
                for note in notes:
                    if "Multi-period" in note:
                        st.warning(f"⚠️ {note}")
                    else:
                        st.info(f"ℹ️ {note}")

                # Per-Chunk audit table
                chunk_vals = ev_val_data.get("chunk_validations", [])
                if chunk_vals:
                    st.markdown("##### Per-Chunk Provenance Findings")
                    audit_rows = []
                    for cv in chunk_vals:
                        audit_rows.append(
                            {
                                "Chunk ID": cv.get("chunk_id"),
                                "Status": cv.get("status"),
                                "Provenance Complete": "✅"
                                if cv.get("provenance_complete")
                                else "❌",
                                "SEC Domain Whitelist": "✅"
                                if cv.get("source_domain_valid")
                                else "❌",
                                "Is Duplicate": "⚠️ Yes"
                                if cv.get("is_duplicate")
                                else "No",
                                "Reporting Period": cv.get("reporting_period") or "N/A",
                                "Warnings": "; ".join(cv.get("warnings", [])) or "None",
                            }
                        )
                    st.table(audit_rows)

    # -------------------------------------------------------------------------
    # View 5: Agent Architecture
    # -------------------------------------------------------------------------
    elif nav_selection == "Agent Architecture":
        st.markdown(
            "### 🤖 Multi-Agent Architecture Blueprint (Session 10 Operational)"
        )
        st.markdown(
            "Finova AI orchestrates specialized agents using LangGraph state graphs to deliver verified financial reports."
        )

        agents = [
            (
                "Supervisor Agent",
                "Deconstructs research questions, classifies intent (5 classes), extracts ticker/period, and plans routes.",
                "Operational",
                "badge-active",
            ),
            (
                "Research Agent",
                "Queries SEC EDGAR with hybrid dense/sparse retrieval and cross-encoder reranking.",
                "Operational",
                "badge-active",
            ),
            (
                "Financial Analyst Agent",
                "Executes deterministic calculations (margins, ratios, cash flows) using structured XBRL facts. Zero LLM math.",
                "Operational",
                "badge-active",
            ),
            (
                "RAG Agent",
                "Synthesizes objective research responses citing statutory filing disclosures [E1] and calculation receipts [C1].",
                "Operational",
                "badge-active",
            ),
            (
                "Verification Agent",
                "Audits numerical claims and dates against evidence citations using strict thresholds to prevent hallucinations.",
                "Operational",
                "badge-active",
            ),
            (
                "Safety Guardrail Node",
                "Enforces safe rejections for unsupported inquiries (trading advice, stock predictions) and withheld responses.",
                "Operational",
                "badge-active",
            ),
        ]

        for name, role, tag, badge_class in agents:
            st.markdown(
                f"""
                <div class="card">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <strong style="font-size: 1.15rem; color: #F8FAFC;">{name}</strong>
                        <span class="{badge_class}">{tag}</span>
                    </div>
                    <p style="color: #94A3B8; margin-top: 0.5rem; margin-bottom: 0;">{role}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # -------------------------------------------------------------------------
    # View 5: Configuration
    # -------------------------------------------------------------------------
    elif nav_selection == "Configuration":
        st.markdown("### ⚙️ System Configuration")
        st.markdown("Loaded from central Pydantic Settings and local environment:")

        config_data = {
            "Application Name": settings.APP_NAME,
            "Environment": settings.APP_ENV,
            "Debug Mode": str(settings.DEBUG),
            "Application Version": settings.APP_VERSION,
            "Backend Host": settings.HOST,
            "Backend Port": settings.PORT,
            "Log Level": settings.LOG_LEVEL,
            "Database URL": settings.DATABASE_URL,
            "SEC User Agent Configured": "Yes" if settings.SEC_USER_AGENT else "No",
            "Filings Storage Directory": settings.FILINGS_STORAGE_DIR,
            "Max Document Size": f"{settings.MAX_DOCUMENT_SIZE_BYTES / (1024 * 1024):.0f} MB",
            "Chunk Target Size": f"{settings.CHUNK_TARGET_SIZE} chars",
            "Chunk Overlap": f"{settings.CHUNK_OVERLAP} chars",
            "Reranker Enabled": "Yes" if settings.RERANKER_ENABLED else "No",
            "Reranker Model": settings.RERANKER_MODEL_NAME,
            "Reranker Device": settings.RERANKER_DEVICE,
            "Reranker Batch Size": str(settings.RERANKER_BATCH_SIZE),
            "Reranker Candidate Count": str(settings.RERANKER_CANDIDATE_COUNT),
            "Evaluation Dataset": settings.RETRIEVAL_EVALUATION_DATASET,
            "Evidence Validation Enabled": "Yes"
            if settings.EVIDENCE_VALIDATION_ENABLED
            else "No",
            "LLM Provider": settings.LLM_PROVIDER,
            "Ollama Base URL": settings.OLLAMA_BASE_URL,
            "Ollama Model": settings.OLLAMA_MODEL,
            "LLM Request Timeout": f"{settings.LLM_REQUEST_TIMEOUT} s",
            "LLM Temperature": str(settings.LLM_TEMPERATURE),
            "LLM Max Tokens": str(settings.LLM_MAX_TOKENS),
            "LLM Context Window": f"{settings.LLM_CONTEXT_WINDOW} tokens",
            "RAG Default Top K": str(settings.RAG_DEFAULT_TOP_K),
            "RAG Minimum Evidence": str(settings.RAG_MINIMUM_EVIDENCE),
            "RAG Max Context Chars": f"{settings.RAG_MAX_CONTEXT_CHARACTERS:,} chars",
        }

        st.table([{"Parameter": k, "Value": str(v)} for k, v in config_data.items()])


if __name__ == "__main__":
    main()
