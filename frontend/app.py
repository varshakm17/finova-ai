"""Finova AI — Minimal Streamlit Frontend Application.

Provides a clean, professional financial analytics interface with dark navy styling,
system health indicators, and SEC EDGAR company & financial metric exploration.
"""

import sys
from pathlib import Path
from typing import Any

import httpx
import streamlit as st

# Ensure project root is in sys.path for relative imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import get_settings

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
    """Query backend health check endpoint safely with a brief timeout.

    Args:
        base_url: Base HTTP address of the FastAPI backend.

    Returns:
        Dict containing health payload if reachable, or None if unavailable.
    """
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
                "Company Lookup (SEC EDGAR)",
                "Research Workspace (Preview)",
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
                    <div class="metric-value">Session 02</div>
                    <p style="color: #94A3B8; font-size: 0.9rem; margin-top: 0.5rem;">
                        SEC EDGAR ingestion pipeline & SQLite financial storage active.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown(
                """
                <div class="card">
                    <div class="metric-label">Multi-Agent Roster</div>
                    <div class="metric-value">6 Agents</div>
                    <p style="color: #94A3B8; font-size: 0.9rem; margin-top: 0.5rem;">
                        Supervisor, Research, Analyst, Calculation, Verification & Report agents.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col3:
            st.markdown(
                """
                <div class="card">
                    <div class="metric-label">SEC Pipeline</div>
                    <div class="metric-value">Live Ingestion</div>
                    <p style="color: #94A3B8; font-size: 0.9rem; margin-top: 0.5rem;">
                        XBRL company facts, 10-K/10-Q submissions, and metric extraction.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("### 🎯 System Objectives & Core Capabilities")
        st.markdown(
            """
            Finova AI is engineered to automate rigorous, evidence-backed corporate financial analysis:
            
            - **Automated SEC EDGAR Retrieval**: Programmatic acquisition of annual (10-K) and quarterly (10-Q) filings.
            - **Structured Metric Extraction**: Accurate parsing of Income Statements, Balance Sheets, and Cash Flow statements.
            - **Deterministic Calculations**: Error-free verification of growth rates, profitability margins, and leverage ratios.
            - **Multi-Year Comparisons**: Longitudinal trend analysis and cross-company benchmarking.
            - **RAG-Powered Question Answering**: Hybrid dense and sparse vector retrieval over corporate footnotes and disclosures.
            - **Hallucination Prevention**: Dedicated verification agent that cross-checks all quantitative claims against primary filing sources.
            """
        )

        st.info(
            "📌 **Session 02 Integration Live**: SEC EDGAR integration pipeline is operational. "
            "Explore company metadata, statutory filings, and extracted XBRL financial metrics in the "
            "**Company Lookup (SEC EDGAR)** section."
        )

    # -------------------------------------------------------------------------
    # View 2: Company Lookup (SEC EDGAR) - Session 02 Feature
    # -------------------------------------------------------------------------
    elif nav_selection == "Company Lookup (SEC EDGAR)":
        st.markdown("### 🏢 SEC EDGAR Company & Financial Data Lookup")
        st.caption(
            "Query official SEC EDGAR submissions and XBRL financial facts by stock ticker."
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

                            tab_filings, tab_metrics = st.tabs(
                                ["📄 SEC Filings", "📈 Financial Observations"]
                            )

                            # Tab 1: Filings
                            with tab_filings:
                                filings_resp = httpx.get(
                                    f"{backend_url}/api/v1/companies/{search_ticker}/filings",
                                    timeout=15.0,
                                )
                                if filings_resp.status_code == 200:
                                    filings_list = filings_resp.json()
                                    if filings_list:
                                        table_data = [
                                            {
                                                "Form": f.get("form"),
                                                "Filing Date": f.get("filing_date"),
                                                "Report Period": f.get("report_date")
                                                or "—",
                                                "Accession Number": f.get(
                                                    "accession_number"
                                                ),
                                                "XBRL": "Yes"
                                                if f.get("is_xbrl")
                                                else "No",
                                                "SEC Archive": f.get("url") or "—",
                                            }
                                            for f in filings_list[:25]
                                        ]
                                        st.dataframe(
                                            table_data, use_container_width=True
                                        )
                                    else:
                                        st.info(
                                            "No recent filings found for this company."
                                        )
                                else:
                                    st.warning("Could not load filings metadata.")

                            # Tab 2: Financial Observations
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

                    except httpx.RequestError as exc:
                        st.error(f"Network error querying backend service: {exc}")

    # -------------------------------------------------------------------------
    # View 3: Research Workspace (Preview)
    # -------------------------------------------------------------------------
    elif nav_selection == "Research Workspace (Preview)":
        st.markdown("### 🔍 Financial Research Workspace (Preview)")
        st.markdown(
            '<span class="badge-planned">Future Session Capability — UI Scaffolding Preview</span>',
            unsafe_allow_html=True,
        )
        st.write("")

        with st.container():
            col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
            with col1:
                st.text_input(
                    "Company Ticker or CIK",
                    value="AAPL",
                    help="Enter a US stock ticker (e.g., AAPL, MSFT, NVDA) or SEC CIK number.",
                    disabled=True,
                )
            with col2:
                st.selectbox(
                    "Filing Type",
                    options=["10-K (Annual)", "10-Q (Quarterly)", "8-K (Current)"],
                    index=0,
                    disabled=True,
                )
            with col3:
                st.selectbox(
                    "Fiscal Year",
                    options=["2024", "2023", "2022", "Multi-Year (3Y)"],
                    index=0,
                    disabled=True,
                )
            with col4:
                st.write("")
                st.write("")
                st.button("Analyze Filing", disabled=True, use_container_width=True)

        st.caption(
            "Note: Advanced multi-agent analysis and report generation will be activated in Sessions 04-06."
        )

        st.markdown("---")
        st.markdown("#### Target Financial Metrics Layout")
        mcol1, mcol2, mcol3, mcol4 = st.columns(4)
        with mcol1:
            st.metric(
                label="Total Revenue",
                value="Extracted in Session 02",
                delta="10-K/10-Q",
            )
        with mcol2:
            st.metric(
                label="Operating Income",
                value="Extracted in Session 02",
                delta="10-K/10-Q",
            )
        with mcol3:
            st.metric(
                label="Free Cash Flow", value="Planned Session 04", delta="Calc Engine"
            )
        with mcol4:
            st.metric(
                label="Debt-to-Equity", value="Planned Session 04", delta="Calc Engine"
            )

    # -------------------------------------------------------------------------
    # View 4: Agent Architecture
    # -------------------------------------------------------------------------
    elif nav_selection == "Agent Architecture":
        st.markdown("### 🤖 Multi-Agent Architecture Blueprint")
        st.markdown(
            "Finova AI orchestrates six specialized agents using LangGraph to deliver verified financial reports."
        )

        agents = [
            (
                "Supervisor Agent",
                "Deconstructs research questions, plans tasks, and routes context between agents.",
                "Orchestrator",
            ),
            (
                "Research Agent",
                "Queries SEC EDGAR, parses HTML/XBRL filings, and retrieves relevant footnote disclosures.",
                "Retrieval",
            ),
            (
                "Financial Analyst Agent",
                "Interprets structured metrics, evaluates trends, and identifies operational risks.",
                "Analysis",
            ),
            (
                "Calculation Agent",
                "Executes deterministic mathematical formulas (CAGR, EBITDA, liquidity, leverage).",
                "Deterministic Math",
            ),
            (
                "Verification Agent",
                "Audits numerical claims against filing citations to prevent hallucinations.",
                "Quality Assurance",
            ),
            (
                "Report Agent",
                "Synthesizes verified findings into professional, evidence-backed research briefs.",
                "Synthesis",
            ),
        ]

        for name, role, tag in agents:
            st.markdown(
                f"""
                <div class="card">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <strong style="font-size: 1.15rem; color: #F8FAFC;">{name}</strong>
                        <span class="badge-planned">{tag}</span>
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
        }

        st.table([{"Parameter": k, "Value": str(v)} for k, v in config_data.items()])


if __name__ == "__main__":
    main()
