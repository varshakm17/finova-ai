"""Finova AI — Minimal Streamlit Frontend Application.

Provides a clean, professional financial analytics interface with dark navy styling,
system health indicators, and a placeholder financial research workspace.
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
            "prior to launching extraction in future sessions."
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
                    <div class="metric-value">Session 01</div>
                    <p style="color: #94A3B8; font-size: 0.9rem; margin-top: 0.5rem;">
                        Core architectural scaffolding, logging, and FastAPI backend active.
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
                    <div class="metric-label">Target Data Source</div>
                    <div class="metric-value">SEC EDGAR</div>
                    <p style="color: #94A3B8; font-size: 0.9rem; margin-top: 0.5rem;">
                        10-K & 10-Q annual/quarterly reports for US-listed public companies.
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
            "📌 **Engineering Foundation Active**: This interface represents the foundational scaffolding "
            "(Session 01). Backend endpoints, logging, configuration management, and automated tests are verified. "
            "Data pipelines and multi-agent graphs will be integrated in subsequent sessions."
        )

    # -------------------------------------------------------------------------
    # View 2: Research Workspace (Preview)
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
            "Note: Live filing retrieval and agent execution will be activated in Session 02 onwards."
        )

        st.markdown("---")
        st.markdown("#### Target Financial Metrics Layout")
        mcol1, mcol2, mcol3, mcol4 = st.columns(4)
        with mcol1:
            st.metric(label="Total Revenue (Planned)", value="—", delta="—")
        with mcol2:
            st.metric(label="Operating Income (Planned)", value="—", delta="—")
        with mcol3:
            st.metric(label="Free Cash Flow (Planned)", value="—", delta="—")
        with mcol4:
            st.metric(label="Debt-to-Equity (Planned)", value="—", delta="—")

    # -------------------------------------------------------------------------
    # View 3: Agent Architecture
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
    # View 4: Configuration
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
