"""Report Generation Agent for Finova AI Multi-Agent Orchestration.

Synthesizes autonomous multi-section financial research briefs combining
retrieved SEC filing disclosures, deterministic calculation receipts,
and multi-period comparative tables in Markdown and HTML.
"""

from __future__ import annotations

import html
import uuid
from datetime import UTC, datetime
from typing import Any

from backend.agents.agent_models import (
    FinancialResearchReport,
    ReportMetadata,
    ReportReference,
    ReportSection,
    ReportTable,
)
from backend.agents.base_agent import BaseFinovaAgent
from backend.agents.state import FinovaAgentState
from backend.llm import get_llm_provider
from backend.llm.llm_provider import LLMProvider
from backend.utils.logger import get_logger
from config.settings import Settings, get_settings

logger = get_logger("report_agent")


class ReportAgent(BaseFinovaAgent):
    """Generates structured, multi-section financial research reports with tables and citations."""

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        super().__init__(
            agent_name="ReportAgent",
            description="Compiles multi-section financial research briefs in Markdown and HTML with verified citations.",
        )
        self.settings = settings or get_settings()
        self.llm = llm_provider or get_llm_provider(settings=self.settings)

    def build_financial_ratios_table(
        self,
        calc_map: dict[str, dict[str, Any]],
    ) -> ReportTable:
        """Create structured table of deterministic financial metrics and ratios."""
        headers = [
            "Metric",
            "Fiscal Period",
            "Calculated Value",
            "Unit",
            "Formula / Citation",
        ]
        rows: list[list[str]] = []

        for cid, cinfo in calc_map.items():
            metric = cinfo.get("metric_name", "").replace("_", " ").title()
            val = cinfo.get("calculated_value")
            unit = cinfo.get("unit", "")
            val_str = (
                f"{val:.2f}%"
                if unit == "percentage" and isinstance(val, (int, float))
                else f"{val:.4f}"
                if isinstance(val, float)
                else str(val)
            )
            fy = f"FY{cinfo.get('fiscal_year', '')}"
            formula = cinfo.get("formula_expression") or cinfo.get("formula_name", "")
            rows.append([metric, fy, val_str, unit, f"[{cid}] ({formula})"])

        return ReportTable(
            title="Deterministic Financial Metrics & Ratios",
            headers=headers,
            rows=rows,
        )

    def build_historical_comparison_table(
        self,
        comparisons: list[dict[str, Any]],
        trends: list[dict[str, Any]],
    ) -> ReportTable:
        """Create structured comparison table across comparative fiscal periods."""
        headers = [
            "Metric",
            "Base Period",
            "Comparison Period",
            "Base Value",
            "Comp Value",
            "Delta",
            "% Change",
        ]
        rows: list[list[str]] = []

        for comp in comparisons:
            metric = comp.get("metric_name", "").replace("_", " ").title()
            bp = comp.get("base_period", "")
            cp = comp.get("comparison_period", "")
            bv = comp.get("base_value", 0.0)
            cv = comp.get("comparison_value", 0.0)
            unit = comp.get("unit", "")
            delta = comp.get("absolute_delta", 0.0)
            pct = comp.get("percentage_delta")

            bv_str = f"{bv:.2f}%" if unit == "percentage" else f"{bv:.2f}"
            cv_str = f"{cv:.2f}%" if unit == "percentage" else f"{cv:.2f}"
            delta_str = f"{delta:+.2f}%" if unit == "percentage" else f"{delta:+.2f}"
            pct_str = f"{pct:+.1f}%" if pct is not None else "N/A"

            rows.append([metric, bp, cp, bv_str, cv_str, delta_str, pct_str])

        return ReportTable(
            title="Multi-Period Comparative Financial Analysis",
            headers=headers,
            rows=rows,
        )

    def format_markdown_table(self, table: ReportTable) -> str:
        """Render a ReportTable into GitHub Flavored Markdown."""
        if not table.rows:
            return "_No comparative numerical data available for this section._\n"

        lines: list[str] = []
        lines.append(f"### {table.title}\n")
        lines.append("| " + " | ".join(table.headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(table.headers)) + " |")
        for row in table.rows:
            clean_cells = [c.replace("|", "/") for c in row]
            lines.append("| " + " | ".join(clean_cells) + " |")
        lines.append("")
        return "\n".join(lines)

    def build_references(
        self,
        evidence_map: dict[str, dict[str, Any]],
        calc_map: dict[str, dict[str, Any]],
    ) -> list[ReportReference]:
        """Compile statutory references for SEC filings and Python calculation receipts."""
        refs: list[ReportReference] = []

        # Calculation receipts
        for cid, cinfo in calc_map.items():
            refs.append(
                ReportReference(
                    ref_type="calculation_receipt",
                    citation_id=cid,
                    filing_name=f"{cinfo.get('metric_name', '')} Calculation",
                    form_type="Deterministic Python Engine",
                    filing_date=datetime.now(UTC).strftime("%Y-%m-%d"),
                    reporting_period=f"FY{cinfo.get('fiscal_year', '')}",
                    accession_number=cinfo.get("calculation_id"),
                    sec_url=None,
                    description=f"{cinfo.get('formula_name', '')}: {cinfo.get('formula_expression', '')}",
                )
            )

        # SEC filing disclosures
        for eid, einfo in evidence_map.items():
            refs.append(
                ReportReference(
                    ref_type="filing_passage",
                    citation_id=eid,
                    filing_name=f"{einfo.get('company_name', '')} {einfo.get('filing_type', '10-K')}",
                    form_type=einfo.get("filing_type", "10-K"),
                    filing_date=einfo.get("filing_date"),
                    reporting_period=einfo.get("filing_date", "")[:4]
                    if einfo.get("filing_date")
                    else None,
                    accession_number=einfo.get("accession_number"),
                    sec_url=einfo.get("source_url"),
                    description=f"Section {einfo.get('section_identifier', 'Disclosures')}",
                )
            )

        return refs

    def assemble_sections(
        self,
        company_name: str,
        ticker: str,
        period: str,
        question: str,
        section_findings: dict[str, list[str]],
        evidence_map: dict[str, dict[str, Any]],
        calc_map: dict[str, dict[str, Any]],
        trends: list[dict[str, Any]],
        comparisons: list[dict[str, Any]],
    ) -> list[ReportSection]:
        """Assemble all canonical research report sections."""
        sections: list[ReportSection] = []
        order = 1

        # 1. Executive Summary
        exec_lines = [
            f"This executive research brief delivers an autonomous financial investigation of **{company_name}** ({ticker}) covering the **{period}** reporting period.",
            f"**Research Objective:** {question}\n",
        ]
        if section_findings.get("executive_summary"):
            exec_lines.extend(section_findings["executive_summary"])
        else:
            exec_lines.append(
                "Analysis conducted across statutory SEC filing disclosures and deterministic computational receipts."
            )
        sections.append(
            ReportSection(
                section_key="executive_summary",
                title="1. Executive Summary",
                order_index=order,
                content_markdown="\n\n".join(exec_lines),
            )
        )
        order += 1

        # 2. Company Overview
        first_eid = next(iter(evidence_map.keys()), "")
        first_cid = next(iter(calc_map.keys()), "")
        overview_lines = [
            f"### Business Profile: {company_name} ({ticker})\n",
        ]
        if section_findings.get("company_overview"):
            overview_lines.extend(section_findings["company_overview"][:4])
        else:
            cite = f" [{first_eid}]" if first_eid else ""
            overview_lines.append(
                f"{company_name} operates within statutory reporting guidelines under SEC jurisdiction{cite}."
            )
        sections.append(
            ReportSection(
                section_key="company_overview",
                title="2. Company Overview & Business Architecture",
                order_index=order,
                content_markdown="\n\n".join(overview_lines),
            )
        )
        order += 1

        # 3. Financial Performance & Key Ratios
        ratios_table = self.build_financial_ratios_table(calc_map)
        ratios_table_md = self.format_markdown_table(ratios_table)
        perf_lines = [
            "All financial metrics, margins, and ratios are calculated using Finova AI's deterministic Python computation engine directly from verified XBRL observations. Zero LLM arithmetic is employed.\n",
            ratios_table_md,
        ]
        if section_findings.get("financial_performance"):
            perf_lines.append("#### Key Performance Highlights\n")
            for f in section_findings["financial_performance"][:6]:
                perf_lines.append(f"- {f}")

        sections.append(
            ReportSection(
                section_key="financial_performance",
                title="3. Financial Performance & Key Ratios",
                order_index=order,
                content_markdown="\n\n".join(perf_lines),
                calculation_ids=list(calc_map.keys()),
                tables=[ratios_table],
            )
        )
        order += 1

        # 4. Historical Multi-Period Comparison & Trends
        comp_table = self.build_historical_comparison_table(comparisons, trends)
        comp_table_md = self.format_markdown_table(comp_table)
        hist_lines = [
            "Longitudinal comparison evaluates changes across consecutive fiscal reporting periods:\n",
            comp_table_md,
        ]
        if trends:
            hist_lines.append("#### Directional Trend Interpretations\n")
            for tr in trends:
                metric = tr.get("metric_name", "").replace("_", " ").title()
                dir_label = tr.get("direction", "")
                notes = tr.get("interpretation_notes", "")
                hist_lines.append(f"- **{metric} ({dir_label})**: {notes}")

        sections.append(
            ReportSection(
                section_key="historical_comparison",
                title="4. Historical Multi-Period Comparison & Trends",
                order_index=order,
                content_markdown="\n\n".join(hist_lines),
                tables=[comp_table] if comp_table.rows else [],
            )
        )
        order += 1

        # 5. Business Operations & MD&A
        mda_lines = [
            "Analysis of operational performance, strategic developments, and management disclosures from Item 7 of statutory filings:\n",
        ]
        if section_findings.get("business_operations_mda"):
            for item in section_findings["business_operations_mda"][:5]:
                mda_lines.append(f"- {item}")
        else:
            mda_lines.append(
                "_No specific MD&A disclosures retrieved for this period._"
            )

        sections.append(
            ReportSection(
                section_key="business_operations_mda",
                title="5. Business Operations & MD&A Disclosures",
                order_index=order,
                content_markdown="\n\n".join(mda_lines),
                evidence_ids=[
                    eid
                    for eid, einfo in evidence_map.items()
                    if "item 7" in einfo.get("section_identifier", "").lower()
                    or "mda" in einfo.get("section_identifier", "").lower()
                ],
            )
        )
        order += 1

        # 6. Risk Factors & Uncertainties
        risk_lines = [
            "Statutory disclosures from SEC Item 1A identifying material risks, competitive challenges, and operational uncertainties:\n",
        ]
        if section_findings.get("risk_factors"):
            for item in section_findings["risk_factors"][:5]:
                risk_lines.append(f"- {item}")
        else:
            risk_lines.append(
                "_No specific risk factor excerpts identified in the target filings._"
            )

        sections.append(
            ReportSection(
                section_key="risk_factors",
                title="6. Risk Factors & Strategic Uncertainties",
                order_index=order,
                content_markdown="\n\n".join(risk_lines),
                evidence_ids=[
                    eid
                    for eid, einfo in evidence_map.items()
                    if "risk" in einfo.get("section_identifier", "").lower()
                    or "1a" in einfo.get("section_identifier", "").lower()
                ],
            )
        )
        order += 1

        # 7. Key Findings & Synthesis
        takeaways = [
            "### Synthesis of Core Evidence\n",
        ]
        if section_findings.get("company_overview"):
            takeaways.append(
                f"1. **Business Architecture:** {section_findings['company_overview'][0]}"
            )
        else:
            takeaways.append(
                f"1. **Corporate Architecture:** {company_name} maintains established market operations documented in statutory SEC submissions."
            )

        if calc_map:
            primary_cid = None
            for cid, cinfo in calc_map.items():
                m_lower = cinfo.get("metric_name", "").lower()
                if "revenue" in m_lower or "margin" in m_lower:
                    primary_cid = cid
                    break
            primary_cid = primary_cid or first_cid
            cinfo = calc_map[primary_cid]
            val = cinfo.get("calculated_value")
            unit = cinfo.get("unit", "")
            val_str = (
                f"{val:.2f}%"
                if unit == "percentage" and isinstance(val, (int, float))
                else f"{val} {unit}"
            )
            m_name = cinfo.get("metric_name", "").replace("_", " ").title()
            takeaways.append(
                f"2. **Financial Performance:** Verified deterministic calculation establishes {m_name} at {val_str} for the target period [{primary_cid}]."
            )

        if section_findings.get("business_operations_mda"):
            takeaways.append(
                f"3. **Operational Dynamics:** {section_findings['business_operations_mda'][0]}"
            )
        elif trends:
            t = trends[0]
            m_name = t.get("metric_name", "").replace("_", " ").title()
            dir_str = t.get("direction", "stable").lower()
            takeaways.append(
                f"3. **Longitudinal Trajectory:** Multi-period trajectory indicates a {dir_str} trend in {m_name} across reporting periods [{first_cid}]."
            )

        if section_findings.get("risk_factors"):
            takeaways.append(
                f"4. **Strategic Risk Profile:** {section_findings['risk_factors'][0]}"
            )
        else:
            takeaways.append(
                "4. **Strategic Risk Profile:** Statutory risk disclosures identify operational and market uncertainties."
            )

        sections.append(
            ReportSection(
                section_key="key_findings",
                title="7. Key Findings & Strategic Takeaways",
                order_index=order,
                content_markdown="\n\n".join(takeaways),
            )
        )
        order += 1

        # 8. Statutory References
        ref_lines = [
            "### Statutory SEC Filings & Computational Provenance\n",
        ]
        for cid, cinfo in calc_map.items():
            metric = cinfo.get("metric_name", "")
            fy = cinfo.get("fiscal_year", "")
            ref_lines.append(
                f"- **[{cid}]**: Deterministic Python receipt for {metric} (FY{fy}) via XBRL facts."
            )
        for eid, einfo in evidence_map.items():
            sec = einfo.get("section_identifier", "")
            acc = einfo.get("accession_number", "N/A")
            dt = einfo.get("filing_date", "N/A")
            ref_lines.append(
                f"- **[{eid}]**: SEC Form {einfo.get('filing_type', '10-K')} (Date: {dt}, Acc: {acc}, Section: {sec})."
            )

        sections.append(
            ReportSection(
                section_key="sources_and_references",
                title="8. Sources & Statutory References",
                order_index=order,
                content_markdown="\n\n".join(ref_lines),
                evidence_ids=list(evidence_map.keys()),
                calculation_ids=list(calc_map.keys()),
            )
        )

        return sections

    def render_markdown(
        self,
        company_name: str,
        ticker: str,
        period: str,
        sections: list[ReportSection],
        verification_status: str = "UNVERIFIED",
    ) -> str:
        """Render complete canonical Markdown research report."""
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        lines: list[str] = [
            f"# Autonomous Financial Research Report: {company_name} ({ticker})",
            f"**Reporting Period:** {period}  ",
            f"**Generated:** {now_str}  ",
            f"**Verification Status:** `{verification_status}`  ",
            "**System:** Finova AI Multi-Agent Autonomous Intelligence Engine  ",
            "\n---\n",
        ]

        for sec in sections:
            lines.append(f"## {sec.title}\n")
            lines.append(sec.content_markdown)
            lines.append("\n---\n")

        return "\n".join(lines)

    def render_html(
        self,
        company_name: str,
        ticker: str,
        period: str,
        sections: list[ReportSection],
        references: list[ReportReference],
        verification_status: str = "UNVERIFIED",
    ) -> str:
        """Render self-contained, publication-ready semantic HTML report with inline executive styles."""
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

        status_color = (
            "#059669"
            if "VERIFIED" in verification_status and "NOT" not in verification_status
            else "#d97706"
        )
        if "REJECTED" in verification_status:
            status_color = "#dc2626"

        html_parts: list[str] = [
            "<!DOCTYPE html>",
            "<html lang='en'>",
            "<head>",
            "<meta charset='utf-8'/>",
            "<meta name='viewport' content='width=device-width, initial-scale=1.0'/>",
            f"<title>Financial Research Brief - {html.escape(company_name)} ({html.escape(ticker)})</title>",
            "<style>",
            "  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #1e293b; background-color: #f8fafc; margin: 0; padding: 24px; }",
            "  .container { max-width: 960px; margin: 0 auto; background: #ffffff; border-radius: 8px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -2px rgba(0,0,0,0.1); padding: 40px; border: 1px solid #e2e8f0; }",
            "  header { border-bottom: 2px solid #0f172a; padding-bottom: 20px; margin-bottom: 30px; }",
            "  h1 { font-size: 28px; color: #0f172a; margin: 0 0 10px 0; font-weight: 700; }",
            "  .meta-bar { display: flex; flex-wrap: wrap; gap: 16px; font-size: 14px; color: #64748b; margin-top: 8px; }",
            "  .badge { display: inline-block; padding: 3px 10px; border-radius: 9999px; font-weight: 600; font-size: 12px; text-transform: uppercase; }",
            f"  .badge-status {{ background-color: {status_color}15; color: {status_color}; border: 1px solid {status_color}; }}",
            "  h2 { font-size: 20px; color: #1e3a8a; border-left: 4px solid #1e3a8a; padding-left: 12px; margin-top: 36px; margin-bottom: 16px; font-weight: 600; }",
            "  h3 { font-size: 16px; color: #334155; margin-top: 20px; margin-bottom: 8px; }",
            "  p, li { font-size: 14px; color: #334155; }",
            "  table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 13px; }",
            "  th, td { border: 1px solid #cbd5e1; padding: 8px 12px; text-align: left; }",
            "  th { background-color: #f1f5f9; color: #1e293b; font-weight: 600; }",
            "  tr:nth-child(even) { background-color: #f8fafc; }",
            "  .citation { color: #2563eb; font-weight: 600; font-family: monospace; }",
            "  footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8; text-align: center; }",
            "</style>",
            "</head>",
            "<body>",
            "<div class='container'>",
            "<header>",
            f"  <h1>Financial Research Brief: {html.escape(company_name)} ({html.escape(ticker)})</h1>",
            "  <div class='meta-bar'>",
            f"    <div><strong>Reporting Period:</strong> {html.escape(period)}</div>",
            f"    <div><strong>Date:</strong> {html.escape(now_str)}</div>",
            f"    <div><span class='badge badge-status'>{html.escape(verification_status)}</span></div>",
            "  </div>",
            "</header>",
            "<main>",
        ]

        for sec in sections:
            html_parts.append(f"<section id='{html.escape(sec.section_key)}'>")
            html_parts.append(f"  <h2>{html.escape(sec.title)}</h2>")

            # Convert markdown tables or content
            sec_md = sec.content_markdown
            # Render tables if present
            if sec.tables:
                for tbl in sec.tables:
                    html_parts.append(f"  <h3>{html.escape(tbl.title)}</h3>")
                    html_parts.append("  <table>")
                    html_parts.append(
                        "    <thead><tr>"
                        + "".join(f"<th>{html.escape(h)}</th>" for h in tbl.headers)
                        + "</tr></thead>"
                    )
                    html_parts.append("    <tbody>")
                    for row in tbl.rows:
                        html_parts.append(
                            "      <tr>"
                            + "".join(f"<td>{html.escape(cell)}</td>" for cell in row)
                            + "</tr>"
                        )
                    html_parts.append("    </tbody>")
                    html_parts.append("  </table>")

            # Simple text conversion for paragraphs
            paragraphs = sec_md.split("\n\n")
            for p in paragraphs:
                p_strip = p.strip()
                if not p_strip or p_strip.startswith("|") or p_strip.startswith("### "):
                    continue
                if p_strip.startswith("- "):
                    items = p_strip.split("\n- ")
                    html_parts.append("  <ul>")
                    for item in items:
                        clean_item = item.lstrip("- ").strip()
                        html_parts.append(f"    <li>{html.escape(clean_item)}</li>")
                    html_parts.append("  </ul>")
                else:
                    html_parts.append(f"  <p>{html.escape(p_strip)}</p>")

            html_parts.append("</section>")

        html_parts.extend(
            [
                "</main>",
                "<footer>",
                f"  Finova AI Autonomous Financial Research Engine &bull; Generated on {html.escape(now_str)} &bull; Deterministic &amp; Auditable",
                "</footer>",
                "</div>",
                "</body>",
                "</html>",
            ]
        )

        return "\n".join(html_parts)

    def execute(self, state: FinovaAgentState) -> dict[str, Any]:
        """Synthesize autonomous financial research brief in Markdown and HTML."""
        question = state.get("user_question", "")
        ticker = state.get("company_ticker") or "TARGET"
        period = state.get("reporting_period") or "Latest Filings"
        plan = state.get("research_plan", {})
        plan_id = (
            plan.get("plan_id")
            if isinstance(plan, dict)
            else getattr(plan, "plan_id", None)
        )
        request_id = state.get("request_id") or str(uuid.uuid4())
        report_id = str(uuid.uuid4())

        consolidated = state.get("consolidated_findings", {})
        evidence_map = consolidated.get("evidence_map", {})
        calc_map = consolidated.get("calculation_map", {})
        section_findings = consolidated.get("section_findings", {})
        trends = consolidated.get("trends", [])
        comparisons = consolidated.get("comparisons", [])
        warnings = list(state.get("warnings", []))

        # Determine company name
        company_name = ticker
        financial_analysis = state.get("financial_analysis")
        if financial_analysis and financial_analysis.get("company_name"):
            company_name = financial_analysis["company_name"]
        elif evidence_map:
            first_ev = next(iter(evidence_map.values()))
            company_name = first_ev.get("company_name") or ticker

        logger.info(
            "ReportAgent assembling research brief for %s (%s) with %d evidence items and %d calculations.",
            company_name,
            ticker,
            len(evidence_map),
            len(calc_map),
        )

        # Assemble canonical sections
        sections = self.assemble_sections(
            company_name=company_name,
            ticker=ticker,
            period=period,
            question=question,
            section_findings=section_findings,
            evidence_map=evidence_map,
            calc_map=calc_map,
            trends=trends,
            comparisons=comparisons,
        )

        # Build auditable references
        references = self.build_references(evidence_map, calc_map)

        # Render Markdown and HTML
        markdown_content = self.render_markdown(
            company_name=company_name,
            ticker=ticker,
            period=period,
            sections=sections,
            verification_status="UNVERIFIED",
        )

        html_content = self.render_html(
            company_name=company_name,
            ticker=ticker,
            period=period,
            sections=sections,
            references=references,
            verification_status="UNVERIFIED",
        )

        metadata = ReportMetadata(
            report_id=report_id,
            request_id=request_id,
            plan_id=plan_id,
            company_name=company_name,
            ticker=ticker,
            title=f"Financial Research Brief: {company_name} ({ticker})",
            reporting_period=period,
            verification_status="UNVERIFIED",
        )

        report = FinancialResearchReport(
            report_id=report_id,
            request_id=request_id,
            plan_id=plan_id,
            ticker=ticker,
            company_name=company_name,
            title=f"Financial Research Brief: {company_name} ({ticker})",
            reporting_period=period,
            status="completed",
            verification_status="UNVERIFIED",
            executive_summary=sections[0].content_markdown if sections else None,
            markdown_content=markdown_content,
            html_content=html_content,
            sections=sections,
            references=references,
            metadata=metadata,
            warnings=warnings,
        )

        return {
            "generated_report": report.model_dump(),
            "report_markdown": markdown_content,
            "report_html": html_content,
            "final_answer": markdown_content,
            "current_step": "report_agent",
            "warnings": warnings,
        }
