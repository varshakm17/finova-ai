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
                "Company Lookup & Ingestion (SEC)",
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
                    <div class="metric-value">Session 03</div>
                    <p style="color: #94A3B8; font-size: 0.9rem; margin-top: 0.5rem;">
                        HTML Ingestion, Section Extractor & Deterministic Text Chunking active.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown(
                """
                <div class="card">
                    <div class="metric-label">Disclosure Sections</div>
                    <div class="metric-value">4 Items</div>
                    <p style="color: #94A3B8; font-size: 0.9rem; margin-top: 0.5rem;">
                        Item 1 (Business), 1A (Risk), 7 (MD&A), 7A (Market Risk).
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col3:
            st.markdown(
                """
                <div class="card">
                    <div class="metric-label">Chunk Provenance</div>
                    <div class="metric-value">Traceable</div>
                    <p style="color: #94A3B8; font-size: 0.9rem; margin-top: 0.5rem;">
                        Every chunk maps to CIK, accession number, section, and character offset.
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
            - **Section-Aware Filing Ingestion**: Full HTML parsing, TOC disambiguation, and boundary-aware extraction of MD&A and Risk Factors.
            - **Deterministic Text Chunking**: Boundary-aware overlapping text chunks preserving paragraph and sentence coherence.
            - **Structured Metric Extraction**: Accurate parsing of Income Statements, Balance Sheets, and Cash Flow statements.
            - **Traceable Provenance**: Every chunk and fact traces directly to its source SEC archive accession and document coordinate.
            """
        )

        st.info(
            "📌 **Session 03 Active**: SEC filing document ingestion, HTML parsing, and section-aware "
            "chunking are fully operational. Visit **Company Lookup & Ingestion (SEC)** to ingest a 10-K or 10-Q filing."
        )

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

                            tab_ingest, tab_filings, tab_metrics, tab_calculations = (
                                st.tabs(
                                    [
                                        "📥 Ingest Filing & View Chunks",
                                        "📄 Available SEC Filings",
                                        "📈 Financial Observations",
                                        "🧮 Financial Analysis & Calculations",
                                    ]
                                )
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
            "Note: Multi-agent orchestration and report synthesis will be activated in Sessions 05-06."
        )

        st.markdown("---")
        st.markdown("#### Target Financial Metrics Layout")
        mcol1, mcol2, mcol3, mcol4 = st.columns(4)
        with mcol1:
            st.metric(
                label="Total Revenue", value="Extracted (XBRL)", delta="Session 02"
            )
        with mcol2:
            st.metric(
                label="Operating Income", value="Extracted (XBRL)", delta="Session 02"
            )
        with mcol3:
            st.metric(
                label="Section Chunks", value="Active (10-K/10-Q)", delta="Session 03"
            )
        with mcol4:
            st.metric(
                label="Free Cash Flow", value="Planned Session 04", delta="Calc Engine"
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
            "Filings Storage Directory": settings.FILINGS_STORAGE_DIR,
            "Max Document Size": f"{settings.MAX_DOCUMENT_SIZE_BYTES / (1024 * 1024):.0f} MB",
            "Chunk Target Size": f"{settings.CHUNK_TARGET_SIZE} chars",
            "Chunk Overlap": f"{settings.CHUNK_OVERLAP} chars",
        }

        st.table([{"Parameter": k, "Value": str(v)} for k, v in config_data.items()])


if __name__ == "__main__":
    main()
