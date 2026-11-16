"""Tests for Research Coordinator Agent (Session 11).

Validates reconciliation of narrative evidence passages and deterministic
calculation receipts, citation mapping (E1, C1), and findings categorization.
"""

from __future__ import annotations

import pytest

from backend.agents.research_coordinator import ResearchCoordinator
from backend.agents.state import FinovaAgentState


@pytest.fixture
def coordinator() -> ResearchCoordinator:
    return ResearchCoordinator()


def test_coordinator_build_evidence_map(coordinator: ResearchCoordinator) -> None:
    """Test deduplicating and indexing evidence chunks with E1, E2 citation IDs."""
    raw_ev = [
        {
            "chunk_id": "chunk_1",
            "text": "Apple designs smartphones.",
            "section_identifier": "ITEM_1",
        },
        {
            "chunk_id": "chunk_2",
            "text": "Global supply chain risks.",
            "section_identifier": "ITEM_1A",
        },
        {
            "chunk_id": "chunk_1",
            "text": "Duplicate chunk_1",
            "section_identifier": "ITEM_1",
        },
    ]
    task_res = [
        {
            "task_id": "t1",
            "retrieved_evidence": [
                {
                    "chunk_id": "chunk_3",
                    "text": "Services revenue grew 9%.",
                    "section_identifier": "ITEM_7",
                }
            ],
        }
    ]

    ev_map, deduped = coordinator.build_evidence_map(raw_ev, task_res)

    assert len(deduped) == 3
    assert len(ev_map) == 3
    assert "E1" in ev_map
    assert "E2" in ev_map
    assert "E3" in ev_map
    assert ev_map["E1"]["chunk_id"] == "chunk_1"
    assert ev_map["E2"]["chunk_id"] == "chunk_2"
    assert ev_map["E3"]["chunk_id"] == "chunk_3"


def test_coordinator_build_calculation_map(coordinator: ResearchCoordinator) -> None:
    """Test indexing valid calculation receipts with C1, C2 citation IDs."""
    calcs = [
        {
            "calculation_id": "calc_01",
            "metric_name": "gross_profit_margin",
            "calculated_value": 44.13,
            "unit": "percentage",
            "fiscal_year": 2023,
            "status": "calculated",
        },
        {
            "calculation_id": "calc_02",
            "metric_name": "invalid_metric",
            "calculated_value": None,
            "status": "unavailable",
        },
        {
            "calculation_id": "calc_03",
            "metric_name": "current_ratio",
            "calculated_value": 0.98,
            "unit": "ratio",
            "fiscal_year": 2023,
            "status": "calculated",
        },
    ]

    calc_map, valid = coordinator.build_calculation_map(calcs)

    assert len(valid) == 2
    assert len(calc_map) == 2
    assert "C1" in calc_map
    assert "C2" in calc_map
    assert calc_map["C1"]["metric_name"] == "gross_profit_margin"
    assert calc_map["C2"]["metric_name"] == "current_ratio"


def test_coordinator_categorize_findings(coordinator: ResearchCoordinator) -> None:
    """Test categorizing findings into calculated, narrative, confirmed, and unresolved."""
    calc_map = {
        "C1": {
            "metric_name": "net_profit_margin",
            "calculated_value": 25.31,
            "unit": "percentage",
            "fiscal_year": 2023,
        }
    }
    ev_map = {
        "E1": {
            "section_identifier": "ITEM_7",
            "text": "Net sales decreased 2.8% due to macroeconomic factors.",
        }
    }
    fin_analysis = {
        "trends": [
            {
                "metric_name": "net_profit_margin",
                "direction": "UPWARD",
                "supporting_receipt_ids": ["c1", "c2"],
            }
        ]
    }

    categorized = coordinator.categorize_findings(
        calc_map=calc_map,
        evidence_map=ev_map,
        financial_analysis=fin_analysis,
        warnings=["Minor XBRL dimension gap."],
    )

    assert len(categorized["calculated"]) == 1
    assert "net_profit_margin" in categorized["calculated"][0]
    assert "[C1]" in categorized["calculated"][0]

    assert len(categorized["narrative"]) == 1
    assert "[E1]" in categorized["narrative"][0]

    assert len(categorized["confirmed"]) == 1
    assert len(categorized["unresolved"]) == 1


def test_coordinator_execute(coordinator: ResearchCoordinator) -> None:
    """Test full execution of coordinator node on agent state."""
    state: FinovaAgentState = {
        "retrieved_evidence": [
            {
                "chunk_id": "c1",
                "text": "Operating expenses rose 1.5%.",
                "section_identifier": "ITEM_7",
            }
        ],
        "calculation_results": [
            {
                "calculation_id": "r1",
                "metric_name": "current_ratio",
                "calculated_value": 1.05,
                "status": "calculated",
                "unit": "ratio",
                "fiscal_year": 2023,
            }
        ],
        "task_results": [],
        "financial_analysis": None,
        "warnings": [],
    }

    res = coordinator.execute(state)
    assert res["current_step"] == "research_coordinator"
    assert "consolidated_findings" in res
    cf = res["consolidated_findings"]
    assert cf["total_evidence_count"] == 1
    assert cf["total_calculation_count"] == 1
