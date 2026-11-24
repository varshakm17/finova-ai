"""SEC XBRL Financial Metric Extractor.

Extracts canonical Income Statement, Balance Sheet, and Cash Flow metrics
from official SEC company facts XBRL payloads.
"""

from typing import Any

from backend.data.data_normalizer import (
    FinancialObservation,
    calculate_duration_days,
    classify_period_type,
    deduplicate_observations,
)
from backend.data.sec_client import normalize_cik
from backend.utils.logger import get_logger

logger = get_logger("financial_extractor")

# Definition of supported canonical metrics and candidate US-GAAP XBRL tags
# Format: (Canonical Name, Statement Type, Is Instant, [Primary Tag, Alternative Tags...])
METRIC_DEFINITIONS: list[tuple[str, str, bool, list[str]]] = [
    # ---------------- Income Statement ----------------
    (
        "Revenue",
        "Income Statement",
        False,
        [
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "Revenues",
            "SalesRevenueNet",
            "SalesRevenueGoodsNet",
            "TotalRevenuesAndOtherIncome",
        ],
    ),
    (
        "Cost of Revenue",
        "Income Statement",
        False,
        [
            "CostOfGoodsAndServicesSold",
            "CostOfRevenue",
            "CostOfGoodsSold",
        ],
    ),
    (
        "Gross Profit",
        "Income Statement",
        False,
        [
            "GrossProfit",
        ],
    ),
    (
        "Operating Income",
        "Income Statement",
        False,
        [
            "OperatingIncomeLoss",
        ],
    ),
    (
        "Net Income",
        "Income Statement",
        False,
        [
            "NetIncomeLoss",
            "ProfitLoss",
        ],
    ),
    (
        "Earnings Per Share",
        "Income Statement",
        False,
        [
            "EarningsPerShareDiluted",
            "EarningsPerShareBasic",
        ],
    ),
    # ---------------- Balance Sheet ----------------
    (
        "Total Assets",
        "Balance Sheet",
        True,
        [
            "Assets",
        ],
    ),
    (
        "Current Assets",
        "Balance Sheet",
        True,
        [
            "AssetsCurrent",
        ],
    ),
    (
        "Total Liabilities",
        "Balance Sheet",
        True,
        [
            "Liabilities",
        ],
    ),
    (
        "Current Liabilities",
        "Balance Sheet",
        True,
        [
            "LiabilitiesCurrent",
        ],
    ),
    (
        "Stockholders' Equity",
        "Balance Sheet",
        True,
        [
            "StockholdersEquity",
            "CommonStockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ],
    ),
    (
        "Cash and Cash Equivalents",
        "Balance Sheet",
        True,
        [
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ],
    ),
    (
        "Long-Term Debt",
        "Balance Sheet",
        True,
        [
            "LongTermDebtNoncurrent",
            "LongTermDebt",
            "LongTermDebtAndCapitalLeaseObligations",
        ],
    ),
    # ---------------- Cash Flow Statement ----------------
    (
        "Operating Cash Flow",
        "Cash Flow Statement",
        False,
        [
            "NetCashProvidedByUsedInOperatingActivities",
        ],
    ),
    (
        "Investing Cash Flow",
        "Cash Flow Statement",
        False,
        [
            "NetCashProvidedByUsedInInvestingActivities",
        ],
    ),
    (
        "Financing Cash Flow",
        "Cash Flow Statement",
        False,
        [
            "NetCashProvidedByUsedInFinancingActivities",
        ],
    ),
    (
        "Capital Expenditures",
        "Cash Flow Statement",
        False,
        [
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsToAcquireProductiveAssets",
            "PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets",
        ],
    ),
]


class FinancialExtractor:
    """Extractor for mapping SEC XBRL company facts into canonical financial observations."""

    def __init__(self) -> None:
        pass

    def extract_company_facts(
        self,
        company_facts: dict[str, Any],
        ticker: str,
        company_name: str | None = None,
    ) -> list[FinancialObservation]:
        """Extract and normalize all available financial metrics from SEC company facts payload.

        Args:
            company_facts: Raw JSON payload from SEC company facts API.
            ticker: Ticker symbol of company.
            company_name: Optional explicit company name; extracted from payload if omitted.

        Returns:
            list[FinancialObservation]: Deduplicated canonical observations.
        """
        raw_cik = company_facts.get("cik")
        if raw_cik is None:
            logger.warning("Company facts missing 'cik' field for ticker %s", ticker)
            return []

        formatted_cik = normalize_cik(raw_cik)
        resolved_name = company_name or company_facts.get("entityName") or ticker
        cik_int = int(formatted_cik)

        facts_us_gaap = company_facts.get("facts", {}).get("us-gaap", {})
        if not facts_us_gaap:
            logger.warning(
                "No 'us-gaap' facts taxonomy found in SEC payload for CIK %s",
                formatted_cik,
            )
            return []

        extracted_records: list[FinancialObservation] = []

        for (
            metric_name,
            statement_type,
            is_instant,
            candidate_tags,
        ) in METRIC_DEFINITIONS:
            # Iterate through candidate tags in order of precedence to capture
            # all reporting periods across SEC taxonomy shifts (e.g. ASC 606 migration).
            metric_records: list[FinancialObservation] = []
            seen_periods: set[tuple[str, str, str]] = set()

            for tag in candidate_tags:
                if tag not in facts_us_gaap:
                    continue
                tag_data = facts_us_gaap[tag]
                units_dict: dict[str, list[dict[str, Any]]] = tag_data.get("units", {})
                if not units_dict:
                    continue

                # Iterate through reported units (e.g., 'USD', 'shares')
                for unit_name, facts_list in units_dict.items():
                    for item in facts_list:
                        # Filter out non-statutory forms (we focus on 10-K, 10-Q, and amendments)
                        form = item.get("form", "")
                        if not form or not form.startswith(("10-K", "10-Q")):
                            continue

                        val = item.get("val")
                        end_date = item.get("end")
                        if val is None or not end_date:
                            continue

                        start_date = item.get("start")
                        filed_date = item.get("filed", end_date)
                        accn = item.get("accn", "")
                        fiscal_year = item.get("fy")
                        fiscal_period = item.get("fp")

                        duration_days = calculate_duration_days(start_date, end_date)
                        period_type = classify_period_type(
                            is_instant=is_instant,
                            duration_days=duration_days,
                            form=form,
                            fiscal_period=fiscal_period,
                        )

                        # Deduplicate by period within this metric, prioritizing earlier candidate tags
                        period_key = (end_date, period_type, start_date or "")
                        if period_key in seen_periods:
                            continue
                        seen_periods.add(period_key)

                        # Build direct archive URL for the filing directory
                        accn_nodash = accn.replace("-", "") if accn else ""
                        source_url = (
                            f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_nodash}/"
                            if accn_nodash
                            else f"https://data.sec.gov/submissions/CIK{formatted_cik}.json"
                        )

                        observation = FinancialObservation(
                            company_ticker=ticker.upper(),
                            company_cik=formatted_cik,
                            company_name=resolved_name,
                            metric_name=metric_name,
                            statement_type=statement_type,
                            original_tag=f"us-gaap:{tag}",
                            numeric_value=float(val),
                            unit=unit_name,
                            period_start=start_date,
                            period_end=end_date,
                            duration_days=duration_days,
                            period_type=period_type,
                            fiscal_year=fiscal_year,
                            fiscal_period=fiscal_period,
                            filing_date=filed_date,
                            filing_type=form,
                            accession_number=accn,
                            source_url=source_url,
                        )
                        metric_records.append(observation)

            extracted_records.extend(metric_records)

        logger.info(
            "Extracted %d raw observations for %s (%s). Deduplicating...",
            len(extracted_records),
            ticker,
            formatted_cik,
        )

        deduped = deduplicate_observations(extracted_records)
        logger.info(
            "Retained %d unique observations after deduplication for %s",
            len(deduped),
            ticker,
        )
        return deduped
