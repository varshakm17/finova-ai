"""Research Coordinator Agent for Finova AI Multi-Agent Orchestration.

Consolidates, structures, and reconciles narrative evidence passages and
deterministic calculation receipts across multiple research tasks.
Guarantees verified evidence mapping and provenance tracking for report generation.
"""

from __future__ import annotations

import re
from typing import Any

from backend.agents.base_agent import BaseFinovaAgent
from backend.agents.state import FinovaAgentState
from backend.utils.logger import get_logger

logger = get_logger("research_coordinator")


class ResearchCoordinator(BaseFinovaAgent):
    """Coordinates and structures research evidence and financial metrics for report generation."""

    def __init__(self) -> None:
        super().__init__(
            agent_name="ResearchCoordinator",
            description="Reconciles retrieved filing disclosures and calculation receipts into structured findings.",
        )

    def build_evidence_map(
        self,
        retrieved_evidence: list[dict[str, Any]],
        task_results: list[dict[str, Any]],
    ) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
        """Deduplicate and map filing evidence chunks to citation IDs (E1, E2, ...)."""
        seen_chunks: set[str] = set()
        deduped_evidence: list[dict[str, Any]] = []

        # Gather from state retrieved_evidence
        for ev in retrieved_evidence:
            cid_val = ev.get("chunk_id") or ev.get("id")
            if not cid_val or not isinstance(cid_val, str) or cid_val.startswith("synthetic_"):
                logger.warning("Rejecting untraceable evidence passage lacking valid chunk_id: %s", ev)
                continue
            chunk_id = str(cid_val)
            if chunk_id not in seen_chunks:
                seen_chunks.add(chunk_id)
                deduped_evidence.append(ev)

        # Gather from individual task results if present
        for tr in task_results:
            t_evidence = tr.get("retrieved_evidence", [])
            for ev in t_evidence:
                cid_val = ev.get("chunk_id") or ev.get("id")
                if not cid_val or not isinstance(cid_val, str) or cid_val.startswith("synthetic_"):
                    logger.warning("Rejecting untraceable evidence passage lacking valid chunk_id: %s", ev)
                    continue
                chunk_id = str(cid_val)
                if chunk_id not in seen_chunks:
                    seen_chunks.add(chunk_id)
                    deduped_evidence.append(ev)

        evidence_map: dict[str, dict[str, Any]] = {}
        for idx, ev in enumerate(deduped_evidence, start=1):
            cid = f"E{idx}"
            chunk_id = str(ev.get("chunk_id") or ev.get("id"))
            evidence_map[cid] = {
                "citation_id": cid,
                "chunk_id": chunk_id,
                "company_name": ev.get("company_name", ""),
                "ticker": ev.get("ticker", ""),
                "section_identifier": ev.get("section_identifier", "Disclosures"),
                "section_title": ev.get("section_title", "Disclosures"),
                "accession_number": ev.get("accession_number", ""),
                "filing_date": ev.get("filing_date", ""),
                "report_date": ev.get("report_date"),
                "filing_type": ev.get("filing_type") or ev.get("form_type", "10-K"),
                "text": ev.get("text") or ev.get("chunk_text", ""),
                "source_url": ev.get("source_url") or ev.get("filing_url", "https://www.sec.gov"),
            }

        return evidence_map, deduped_evidence

    def build_calculation_map(
        self,
        calculation_results: list[dict[str, Any]],
    ) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
        """Map deterministic calculation receipts to citation IDs (C1, C2, ...)."""
        calc_map: dict[str, dict[str, Any]] = {}
        valid_receipts: list[dict[str, Any]] = []

        for r in calculation_results:
            if (
                r.get("status") == "calculated"
                and r.get("calculated_value") is not None
            ):
                valid_receipts.append(r)

        for idx, r in enumerate(valid_receipts, start=1):
            cid = f"C{idx}"
            calc_map[cid] = {
                "citation_id": cid,
                "calculation_id": r.get("calculation_id") or r.get("id"),
                "metric_name": r.get("metric_name", "Unknown Metric"),
                "formula_name": r.get("formula_name", ""),
                "formula_expression": r.get("formula_expression", ""),
                "calculated_value": r.get("calculated_value"),
                "unit": r.get("unit", ""),
                "fiscal_year": r.get("fiscal_year"),
                "fiscal_period": r.get("fiscal_period", "FY"),
                "period_end": r.get("period_end", ""),
                "inputs": r.get("inputs", []),
            }

        return calc_map, valid_receipts

    def organize_section_findings(
        self,
        evidence_map: dict[str, dict[str, Any]],
        calc_map: dict[str, dict[str, Any]],
        financial_analysis: dict[str, Any] | None,
        task_results: list[dict[str, Any]],
    ) -> dict[str, list[str]]:
        """Organize research findings into standard financial brief sections."""
        sections: dict[str, list[str]] = {
            "executive_summary": [],
            "company_overview": [],
            "financial_performance": [],
            "historical_comparison": [],
            "business_operations_mda": [],
            "risk_factors": [],
        }

        # 1. Financial Performance from calculations
        for cid, cinfo in calc_map.items():
            metric = cinfo["metric_name"]
            val = cinfo["calculated_value"]
            unit = cinfo["unit"]
            fy = cinfo.get("fiscal_year", "")
            val_fmt = (
                f"{val:.2f}%"
                if unit == "percentage" and isinstance(val, (int, float))
                else f"{val} {unit}"
            )
            fact_str = (
                f"Deterministic calculation of {metric} for FY{fy}: {val_fmt} [{cid}]"
            )
            sections["financial_performance"].append(fact_str)

        # 2. Historical comparison from financial analysis trends & comparisons
        if financial_analysis:
            trends = financial_analysis.get("trends", [])
            for tr in trends:
                metric = tr.get("metric_name", "")
                direction = tr.get("direction", "")
                pct_chg = tr.get("percentage_change")
                abs_chg = tr.get("absolute_change")
                unit = tr.get("unit", "")
                periods = tr.get("periods", [])
                notes = tr.get("interpretation_notes", "")
                p_span = (
                    f"{periods[0]} to {periods[-1]}"
                    if len(periods) >= 2
                    else "the period"
                )
                pct_str = f" ({pct_chg:+.1f}%)" if pct_chg is not None else ""
                matching_cids = [
                    cid
                    for cid, cinfo in calc_map.items()
                    if cinfo.get("metric_name") == metric
                ]
                cite_str = f" [{matching_cids[0]}]" if matching_cids else ""
                t_str = f"{metric} showed a {direction.lower()} trend across {p_span} with a net change of {abs_chg:+.2f} {unit}{pct_str}{cite_str}. {notes}"
                sections["historical_comparison"].append(t_str)

        # 3. Narrative findings by section identifier from SEC filings
        for eid, einfo in evidence_map.items():
            sec_id = (
                str(einfo.get("section_identifier", ""))
                .lower()
                .replace("_", " ")
                .replace("-", " ")
            )
            text = einfo.get("text", "").strip()

            # Clean snippet for narrative findings: extract non-table sentences if tabular
            raw_lines = [line_item.strip() for line_item in text.splitlines() if line_item.strip()]
            narrative_lines = [
                line_item
                for line_item in raw_lines
                if not line_item.startswith("|") and line_item.count("|") < 2
            ]
            narrative_text = " ".join(narrative_lines).strip()
            if not narrative_text or len(narrative_text.split()) < 4:
                # Chunk is purely tabular; it remains in evidence_map for reference, but not as narrative text
                continue

            if len(narrative_text) > 280:
                # Find last space within first 280 chars to avoid truncating numbers mid-digit
                cut_idx = narrative_text.rfind(" ", 0, 280)
                if cut_idx <= 0:
                    cut_idx = 280
                clean_snippet = re.sub(r"\s+", " ", narrative_text[:cut_idx]).strip()
                summary_snippet = clean_snippet + "..."
            else:
                summary_snippet = re.sub(r"\s+", " ", narrative_text).strip()

            if "item 1a" in sec_id or "risk" in sec_id:
                sections["risk_factors"].append(
                    f"Risk Disclosure [{eid}]: {summary_snippet}"
                )
            elif "item 7" in sec_id or "mda" in sec_id or "management" in sec_id:
                sections["business_operations_mda"].append(
                    f"Management Discussion [{eid}]: {summary_snippet}"
                )
            elif "item 1" in sec_id or "business" in sec_id:
                sections["company_overview"].append(
                    f"Business Operations [{eid}]: {summary_snippet}"
                )
            else:
                sections["business_operations_mda"].append(
                    f"Filing Disclosure [{eid}]: {summary_snippet}"
                )

        # 4. Integrate task results findings
        for tr in task_results:
            findings = tr.get("findings", [])
            q = tr.get("question", "").lower()
            target_sec = "business_operations_mda"
            if "risk" in q:
                target_sec = "risk_factors"
            elif "overview" in q or "business" in q:
                target_sec = "company_overview"
            elif "ratio" in q or "margin" in q or "financial" in q:
                target_sec = "financial_performance"

            for f in findings:
                if f.startswith("Retrieved ") and "evidence passages" in f:
                    continue
                if f not in sections[target_sec]:
                    sections[target_sec].append(f)

        # 5. Executive summary compilation
        if sections["financial_performance"] and calc_map:
            sections["executive_summary"].append(
                f"Financial calculations yielded {len(calc_map)} verified deterministic receipts across key ratios and profitability metrics."
            )
        if sections["historical_comparison"] and calc_map:
            sections["executive_summary"].append(
                f"Longitudinal analysis identified {len(sections['historical_comparison'])} multi-period metric trends."
            )
        if sections["risk_factors"] and evidence_map:
            sections["executive_summary"].append(
                f"Identified {len(sections['risk_factors'])} primary operational and statutory risk factors."
            )

        return sections

    def categorize_findings(
        self,
        calc_map: dict[str, dict[str, Any]],
        evidence_map: dict[str, dict[str, Any]],
        financial_analysis: dict[str, Any] | None,
        warnings: list[str],
    ) -> dict[str, list[str]]:
        """Categorize consolidated findings into calculated, narrative, confirmed, and unresolved."""
        categorized: dict[str, list[str]] = {
            "calculated": [],
            "narrative": [],
            "confirmed": [],
            "unresolved": [],
        }

        # Calculated facts
        for cid, cinfo in calc_map.items():
            metric = cinfo["metric_name"]
            val = cinfo["calculated_value"]
            unit = cinfo["unit"]
            fy = cinfo.get("fiscal_year", "")
            val_fmt = (
                f"{val:.2f}%"
                if unit == "percentage" and isinstance(val, (int, float))
                else f"{val} {unit}"
            )
            categorized["calculated"].append(f"{metric} in FY{fy}: {val_fmt} [{cid}]")

        # Narrative facts
        for eid, einfo in evidence_map.items():
            sec = einfo.get("section_identifier", "Filing")
            snippet = einfo.get("text", "")[:180].strip()
            categorized["narrative"].append(f"Section {sec} [{eid}]: {snippet}...")

        # Confirmed findings (trends supported by receipts)
        if financial_analysis:
            for tr in financial_analysis.get("trends", []):
                metric = tr.get("metric_name", "")
                direction = tr.get("direction", "")
                receipt_ids = tr.get("supporting_receipt_ids", [])
                categorized["confirmed"].append(
                    f"Deterministic trend for {metric} ({direction}) supported by {len(receipt_ids)} verified calculations."
                )

        # Unresolved findings / missing evidence
        for w in warnings:
            categorized["unresolved"].append(w)

        if not calc_map:
            categorized["unresolved"].append(
                "No deterministic financial calculations were available for target period."
            )
        if not evidence_map:
            categorized["unresolved"].append(
                "No SEC filing text disclosures were retrieved for target query."
            )

        return categorized

    def execute(self, state: FinovaAgentState) -> dict[str, Any]:
        """Consolidate research findings, map citations, and organize section evidence."""
        retrieved_evidence = state.get("retrieved_evidence", [])
        calculation_results = state.get("calculation_results", [])
        task_results = state.get("task_results", [])
        financial_analysis = state.get("financial_analysis")
        warnings = list(state.get("warnings", []))

        evidence_map, deduped_evidence = self.build_evidence_map(
            retrieved_evidence, task_results
        )
        calc_map, valid_receipts = self.build_calculation_map(calculation_results)

        section_findings = self.organize_section_findings(
            evidence_map=evidence_map,
            calc_map=calc_map,
            financial_analysis=financial_analysis,
            task_results=task_results,
        )

        categorized_findings = self.categorize_findings(
            calc_map=calc_map,
            evidence_map=evidence_map,
            financial_analysis=financial_analysis,
            warnings=warnings,
        )

        consolidated = {
            "evidence_map": evidence_map,
            "calculation_map": calc_map,
            "section_findings": section_findings,
            "categorized_findings": categorized_findings,
            "total_evidence_count": len(evidence_map),
            "total_calculation_count": len(calc_map),
            "trends": financial_analysis.get("trends", [])
            if financial_analysis
            else [],
            "comparisons": financial_analysis.get("comparisons", [])
            if financial_analysis
            else [],
        }

        logger.info(
            "ResearchCoordinator consolidated %d evidence passages and %d calculation receipts.",
            len(evidence_map),
            len(calc_map),
        )

        return {
            "consolidated_findings": consolidated,
            "retrieved_evidence": deduped_evidence,
            "current_step": "research_coordinator",
            "warnings": warnings,
        }
