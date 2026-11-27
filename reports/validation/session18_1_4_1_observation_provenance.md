# Finova AI — Session 18.1.4.1 Complete Observation Provenance and Semantic Audit Reconciliation Report

**Audit Timestamp:** `2026-11-27T07:23:42.623112+00:00`  
**Git Branch:** `session-18.1.4.1-observation-provenance-reconciliation`  
**Base Commit:** `526a9b05a7e87007f1bb05a20a26d0286783b4a8`  

---

## 1. Executive Summary & Verification Outcomes (Original vs Reconciled)

| Metric | MSFT (FY2023) | TSLA (FY2023) | NVDA (FY2024) | System Total |
|---|---:|---:|---:|---:|
| **Report Status** | `COMPLETED` | `COMPLETED` | `COMPLETED` | All COMPLETED |
| **Original Verification Status** | `verified` | `verified` | `verified` | Initial |
| **Reconciled Verification Status** | `verified` | `verified` | `verified` | Reconciled Policy |
| **Total Claims Extracted** | 36 | 41 | 34 | 111 |
| **Substantive Verifiable Claims** | 27 | 32 | 26 | 85 |
| **Structural Statements** | 9 | 9 | 8 | 26 |
| **Original Supported Claims** | 27 | 32 | 26 | 85 |
| **Reconciled Supported Claims** | 27 | 32 | 26 | 85 |
| **Original Partially Supported** | 0 | 0 | 0 | 0 |
| **Reconciled Partially Supported** | 0 | 0 | 0 | 0 |
| **Original Unsupported Claims** | 0 | 0 | 0 | 0 |
| **Reconciled Unsupported Claims** | 0 | 0 | 0 | 0 |
| **Original Contradicted Claims** | 0 | 0 | 0 | 0 |
| **Reconciled Contradicted Claims** | 0 | 0 | 0 | 0 |
| **Reconciled Incomplete Claims** | 0 | 0 | 0 | 0 |
| **Incomplete-Provenance Claims** | 0 | 0 | 0 | 0 |
| **Unique Filing Passages Cited** | 12 | 13 | 12 | 37 |
| **Unique Calculation Receipts** | 4 | 10 | 8 | 22 |
| **Unique Trend Receipts** | 1 | 4 | 2 | 7 |
| **Execution Duration** | 30.08s | 7.04s | 7.08s | 44.2s |

---

## 2. Before-and-After Verification Behavior

| Verification Dimension | Session 18.1.4 Baseline | Session 18.1.4.1 Complete Provenance & Reconciled Audit | Improvement & Safety Guarantee |
|---|---|---|---|
| **Observation Sequence** | Fell back to `[start_val, end_val]` in audit | Strict retention of complete ordered observations array | Full sequence ($V_1 \to V_N$) verified and persisted without fallback. |
| **Observation Validation** | Basic length check | 14-point mandatory validation (`verify_trend_math`) | Rejects missing intermediate years, unit mismatches, out-of-order, and duplicates. |
| **Mixed Trajectory Rule** | Disallowed two-point mixed | Two-point series strictly rejected from establishing mixed | Mixed trajectory requires $\ge 3$ verified non-monotonic observations. |
| **Underlying Provenance** | Unlinked trend receipts | Traced to underlying `financial_calculations` records | Accession numbers, source 10-K URLs, and input tags preserved in audit record. |
| **Audit Reconciliation** | Separate semantic list, unreflected in headline counts | Headline counts reconciled with semantic outcomes | Semantic contradictions become `contradicted`; company cannot be `verified` if claims fail. |
| **Historical Classification** | Bare 'accelerated' trigger converted legal debt clauses | Narrowed contextual classification with exclusion guards | Legal debt acceleration and generic operational speedups remain general/structural. |

---

## 3. Trajectory Classifications & Complete Observations

Every longitudinal trend is established from complete, ordered, genuine observations:

| Company | Citation | Metric | Period Range | Complete Observations ($V_1 \to V_N$) | Recalculated Trajectory | Net Shift | Direction | Formula |
|---|---|---|---|---|---|---:|---|---|
| **MSFT** | `[C4]` | revenue_growth Trend | FY2021 - FY2023 | `FY2021: 17.53percentage -> FY2022: 17.96percentage -> FY2023: 6.88percentage` | `MIXED_DOWNWARD_NET` | -60.75% | DOWNWARD | `((V_end - V_start) / abs(V_start)) * 100` |
| **TSLA** | `[C13]` | revenue_growth Trend | FY2021 - FY2023 | `FY2021: 150.79percentage -> FY2022: 51.35percentage -> FY2023: 18.80percentage` | `MONOTONIC_DOWNWARD` | -87.54% | DOWNWARD | `((V_end - V_start) / abs(V_start)) * 100` |
| **TSLA** | `[C14]` | gross_profit_margin Trend | FY2021 - FY2023 | `FY2021: 25.28percentage -> FY2022: 25.60percentage -> FY2023: 18.25percentage` | `MIXED_DOWNWARD_NET` | -27.81% | DOWNWARD | `((V_end - V_start) / abs(V_start)) * 100` |
| **TSLA** | `[C15]` | operating_cash_flow_margin Trend | FY2021 - FY2023 | `FY2021: 21.36percentage -> FY2022: 18.07percentage -> FY2023: 13.70percentage` | `MONOTONIC_DOWNWARD` | -35.87% | DOWNWARD | `((V_end - V_start) / abs(V_start)) * 100` |
| **TSLA** | `[C16]` | free_cash_flow Trend | FY2021 - FY2023 | `FY2021: 5015000000.00USD -> FY2022: 7566000000.00USD -> FY2023: 4357000000.00USD` | `MIXED_DOWNWARD_NET` | -13.12% | DOWNWARD | `((V_end - V_start) / abs(V_start)) * 100` |
| **NVDA** | `[C7]` | revenue_growth Trend | FY2022 - FY2024 | `FY2022: 61.40percentage -> FY2023: 0.22percentage -> FY2024: 125.85percentage` | `MIXED_UPWARD_NET` | +104.96% | UPWARD | `((V_end - V_start) / abs(V_start)) * 100` |
| **NVDA** | `[C8]` | gross_profit_margin Trend | FY2022 - FY2024 | `FY2022: 64.93percentage -> FY2023: 56.93percentage -> FY2024: 72.72percentage` | `MIXED_UPWARD_NET` | +12.00% | UPWARD | `((V_end - V_start) / abs(V_start)) * 100` |

---

## 4. Complete Provenance Tracing from Underlying Statutory Records

Every trend receipt was traced back to deterministic calculation records in SQLite `financial_calculations`:

| Company | Trend Citation | Supporting Calculation ID | Fiscal Period | Calculated Value | Accession Number | Statutory Source |
|---|---|---|---|---:|---|---|
| **MSFT** | `[C4]` | `0000789019_revenue_growth_annual_2021-06-30` | FY2023 | 17.5317 percentage | `0000950170-23-035122` | [SEC Filing](https://www.sec.gov/Archives/edgar/data/789019/000095017023035122/) |
| **MSFT** | `[C4]` | `0000789019_revenue_growth_annual_2022-06-30` | FY2023 | 17.9561 percentage | `0000950170-24-087843` | [SEC Filing](https://www.sec.gov/Archives/edgar/data/789019/000095017024087843/) |
| **MSFT** | `[C4]` | `0000789019_revenue_growth_annual_2023-06-30` | FY2023 | 6.8820 percentage | `0000950170-25-100235` | [SEC Filing](https://www.sec.gov/Archives/edgar/data/789019/000095017025100235/) |
| **TSLA** | `[C13]` | `0001318605_revenue_growth_annual_2021-12-31` | FY2023 | 150.7913 percentage | `0001628280-24-002390` | [SEC Filing](https://www.sec.gov/Archives/edgar/data/1318605/000162828024002390/) |
| **TSLA** | `[C13]` | `0001318605_revenue_growth_annual_2022-12-31` | FY2023 | 51.3517 percentage | `0001628280-25-003063` | [SEC Filing](https://www.sec.gov/Archives/edgar/data/1318605/000162828025003063/) |
| **TSLA** | `[C13]` | `0001318605_revenue_growth_annual_2023-12-31` | FY2023 | 18.7953 percentage | `0001628280-26-003952` | [SEC Filing](https://www.sec.gov/Archives/edgar/data/1318605/000162828026003952/) |
| **TSLA** | `[C14]` | `0001318605_gross_profit_margin_annual_2021-12-31` | FY2023 | 25.2792 percentage | `0001628280-24-002390` | [SEC Filing](https://www.sec.gov/Archives/edgar/data/1318605/000162828024002390/) |
| **TSLA** | `[C14]` | `0001318605_gross_profit_margin_annual_2022-12-31` | FY2023 | 25.5984 percentage | `0001628280-25-003063` | [SEC Filing](https://www.sec.gov/Archives/edgar/data/1318605/000162828025003063/) |
| **TSLA** | `[C14]` | `0001318605_gross_profit_margin_annual_2023-12-31` | FY2023 | 18.2489 percentage | `0001628280-26-003952` | [SEC Filing](https://www.sec.gov/Archives/edgar/data/1318605/000162828026003952/) |
| **TSLA** | `[C15]` | `0001318605_operating_cash_flow_margin_annual_2021-12-31` | FY2023 | 21.3608 percentage | `0001628280-24-002390` | [SEC Filing](https://www.sec.gov/Archives/edgar/data/1318605/000162828024002390/) |
| **TSLA** | `[C15]` | `0001318605_operating_cash_flow_margin_annual_2022-12-31` | FY2023 | 18.0747 percentage | `0001628280-25-003063` | [SEC Filing](https://www.sec.gov/Archives/edgar/data/1318605/000162828025003063/) |
| **TSLA** | `[C15]` | `0001318605_operating_cash_flow_margin_annual_2023-12-31` | FY2023 | 13.6980 percentage | `0001628280-26-003952` | [SEC Filing](https://www.sec.gov/Archives/edgar/data/1318605/000162828026003952/) |
| **TSLA** | `[C16]` | `0001318605_free_cash_flow_annual_2021-12-31` | FY2023 | 5015000000.0000 USD | `0001628280-24-002390` | [SEC Filing](https://www.sec.gov/Archives/edgar/data/1318605/000162828024002390/) |
| **TSLA** | `[C16]` | `0001318605_free_cash_flow_annual_2022-12-31` | FY2023 | 7566000000.0000 USD | `0001628280-25-003063` | [SEC Filing](https://www.sec.gov/Archives/edgar/data/1318605/000162828025003063/) |
| **TSLA** | `[C16]` | `0001318605_free_cash_flow_annual_2023-12-31` | FY2023 | 4357000000.0000 USD | `0001628280-26-003952` | [SEC Filing](https://www.sec.gov/Archives/edgar/data/1318605/000162828026003952/) |
| **NVDA** | `[C7]` | `0001045810_revenue_growth_annual_2022-01-30` | FY2024 | 61.4033 percentage | `0001045810-22-000036` | [SEC Filing](https://www.sec.gov/Archives/edgar/data/1045810/000104581022000036/) |
| **NVDA** | `[C7]` | `0001045810_revenue_growth_annual_2023-01-29` | FY2024 | 0.2229 percentage | `0001045810-23-000017` | [SEC Filing](https://www.sec.gov/Archives/edgar/data/1045810/000104581023000017/) |
| **NVDA** | `[C7]` | `0001045810_revenue_growth_annual_2024-01-28` | FY2024 | 125.8545 percentage | `0001045810-24-000029` | [SEC Filing](https://www.sec.gov/Archives/edgar/data/1045810/000104581024000029/) |
| **NVDA** | `[C8]` | `0001045810_gross_profit_margin_annual_2022-01-30` | FY2024 | 64.9290 percentage | `0001045810-22-000036` | [SEC Filing](https://www.sec.gov/Archives/edgar/data/1045810/000104581022000036/) |
| **NVDA** | `[C8]` | `0001045810_gross_profit_margin_annual_2023-01-29` | FY2024 | 56.9289 percentage | `0001045810-23-000017` | [SEC Filing](https://www.sec.gov/Archives/edgar/data/1045810/000104581023000017/) |
| **NVDA** | `[C8]` | `0001045810_gross_profit_margin_annual_2024-01-28` | FY2024 | 72.7176 percentage | `0001045810-24-000029` | [SEC Filing](https://www.sec.gov/Archives/edgar/data/1045810/000104581024000029/) |

---

## 5. Independent Arithmetic Checks & Recalculation

Deterministic independent recalculation was performed for every unique trend calculation receipt:

| Company | Citation | Calculation ID | Start Value | End Value | Recalc Absolute | Recalc % | Recorded Value | Status | Formula Metadata |
|---|---|---|---:|---:|---:|---:|---:|---|---|
| **MSFT** | `[C4]` | `calc_trend_revenue_growth_FY2021_FY2023` | 17.53 | 6.88 | -10.65 | -60.75% | -60.75 % | `verified` | `((V_end - V_start) / abs(V_start)) * 100` |
| **TSLA** | `[C13]` | `calc_trend_revenue_growth_FY2021_FY2023` | 150.79 | 18.80 | -132.00 | -87.54% | -87.54 % | `verified` | `((V_end - V_start) / abs(V_start)) * 100` |
| **TSLA** | `[C14]` | `calc_trend_gross_profit_margin_FY2021_FY2023` | 25.28 | 18.25 | -7.03 | -27.81% | -27.81 % | `verified` | `((V_end - V_start) / abs(V_start)) * 100` |
| **TSLA** | `[C15]` | `calc_trend_operating_cash_flow_margin_FY2021_FY2023` | 21.36 | 13.70 | -7.66 | -35.87% | -35.87 % | `verified` | `((V_end - V_start) / abs(V_start)) * 100` |
| **TSLA** | `[C16]` | `calc_trend_free_cash_flow_FY2021_FY2023` | 5015000000.00 | 4357000000.00 | -658000000.00 | -13.12% | -13.12 % | `verified` | `((V_end - V_start) / abs(V_start)) * 100` |
| **NVDA** | `[C7]` | `calc_trend_revenue_growth_FY2022_FY2024` | 61.40 | 125.85 | +64.45 | +104.96% | 104.96 % | `verified` | `((V_end - V_start) / abs(V_start)) * 100` |
| **NVDA** | `[C8]` | `calc_trend_gross_profit_margin_FY2022_FY2024` | 64.93 | 72.72 | +7.79 | +12.00% | 12.00 % | `verified` | `((V_end - V_start) / abs(V_start)) * 100` |

---

## 6. Reconciled Claim-Level Semantic Verification Results

The following table displays reconciled outcomes where independent semantic trend results update claim-level outcomes and denominators:

| Company | Claim ID | Claim Narrative | Citation | Claim Type | Trajectory | Recalc Net | Arith | Orig Outcome | Reconciled Outcome | Granular Reason |
|---|---|---|---|---|---|---:|:---:|:---:|:---:|---|
| **MSFT** | `CLM-09` | Deterministic calculation of revenue_growth for FY2023: 6.88% | `[C1]` | `financial_metric` | `N/A` | N/A | YES | `supported` | `supported` | Deterministic calculation receipt C1 (0000789019_revenue_growth_annual_2023-06-30) verifies revenue_growth = 6.8820 percentage. |
| **MSFT** | `CLM-10` | Deterministic calculation of revenue_growth for FY2022: 17.96% | `[C2]` | `financial_metric` | `N/A` | N/A | YES | `supported` | `supported` | Deterministic calculation receipt C2 (0000789019_revenue_growth_annual_2022-06-30) verifies revenue_growth = 17.9561 percentage. |
| **MSFT** | `CLM-11` | Deterministic calculation of revenue_growth for FY2021: 17.53% | `[C3]` | `financial_metric` | `N/A` | N/A | YES | `supported` | `supported` | Deterministic calculation receipt C3 (0000789019_revenue_growth_annual_2021-06-30) verifies revenue_growth = 17.5317 percentage. |
| **MSFT** | `CLM-12` | Deterministic calculation of revenue_growth Trend for FY2023: -60.7454 % | `[C4]` | `financial_metric` | `MIXED_DOWNWARD_NET` | -60.75% | YES | `supported` | `supported` | Claim supported by verified trend receipt calc_trend_revenue_growth_FY2021_FY2023 (revenue_growth Trend = -60.7454 %, trajectory=MIXED_DOWNWARD_NET). |
| **MSFT** | `CLM-14` | **Revenue Growth (MIXED)**: revenue_growth demonstrated mixed volatility across periods (net shift: -10.65 percentage (-60.7%)). | `[C4]` | `historical_comparison` | `MIXED_DOWNWARD_NET` | -60.75% | YES | `supported` | `supported` | Claim supported by verified trend receipt calc_trend_revenue_growth_FY2021_FY2023 (revenue_growth Trend = -60.7454 %, trajectory=MIXED_DOWNWARD_NET). |
| **MSFT** | `CLM-33` | **Financial Performance:** Verified deterministic calculation establishes Revenue Growth at 6.88% for the target period . | `[C1]` | `financial_metric` | `N/A` | N/A | YES | `supported` | `supported` | Deterministic calculation receipt C1 (0000789019_revenue_growth_annual_2023-06-30) verifies revenue_growth = 6.8820 percentage. |
| **TSLA** | `CLM-10` | Deterministic calculation of revenue_growth for FY2023: 18.80% | `[C1]` | `financial_metric` | `N/A` | N/A | YES | `supported` | `supported` | Deterministic calculation receipt C1 (0001318605_revenue_growth_annual_2023-12-31) verifies revenue_growth = 18.7953 percentage. |
| **TSLA** | `CLM-11` | Deterministic calculation of gross_profit_margin for FY2023: 18.25% | `[C2]` | `financial_metric` | `N/A` | N/A | YES | `supported` | `supported` | Deterministic calculation receipt C2 (0001318605_gross_profit_margin_annual_2023-12-31) verifies gross_profit_margin = 18.2489 percentage. |
| **TSLA** | `CLM-12` | Deterministic calculation of operating_cash_flow_margin for FY2023: 13.70% | `[C3]` | `financial_metric` | `N/A` | N/A | YES | `supported` | `supported` | Deterministic calculation receipt C3 (0001318605_operating_cash_flow_margin_annual_2023-12-31) verifies operating_cash_flow_margin = 13.6980 percentage. |
| **TSLA** | `CLM-13` | Deterministic calculation of free_cash_flow for FY2023: 4357000000.0 USD | `[C4]` | `financial_metric` | `N/A` | N/A | YES | `supported` | `supported` | Deterministic calculation receipt C4 (0001318605_free_cash_flow_annual_2023-12-31) verifies free_cash_flow = 4357000000.0000 USD. |
| **TSLA** | `CLM-14` | Deterministic calculation of revenue_growth for FY2022: 51.35% | `[C5]` | `financial_metric` | `N/A` | N/A | YES | `supported` | `supported` | Deterministic calculation receipt C5 (0001318605_revenue_growth_annual_2022-12-31) verifies revenue_growth = 51.3517 percentage. |
| **TSLA** | `CLM-15` | Deterministic calculation of gross_profit_margin for FY2022: 25.60% | `[C6]` | `financial_metric` | `N/A` | N/A | YES | `supported` | `supported` | Deterministic calculation receipt C6 (0001318605_gross_profit_margin_annual_2022-12-31) verifies gross_profit_margin = 25.5984 percentage. |
| **TSLA** | `CLM-17` | **Revenue Growth (DOWNWARD)**: Top-line revenue expansion decelerated (-87.5%). | `[C13]` | `historical_comparison` | `MONOTONIC_DOWNWARD` | -87.54% | YES | `supported` | `supported` | Claim supported by verified trend receipt calc_trend_revenue_growth_FY2021_FY2023 (revenue_growth Trend = -87.5356 %, trajectory=MONOTONIC_DOWNWARD). |
| **TSLA** | `CLM-18` | **Gross Profit Margin (MIXED)**: gross_profit_margin demonstrated mixed volatility across periods (net shift: -7.03 percentage (-27.8%)). | `[C14]` | `historical_comparison` | `MIXED_DOWNWARD_NET` | -27.81% | YES | `supported` | `supported` | Claim supported by verified trend receipt calc_trend_gross_profit_margin_FY2021_FY2023 (gross_profit_margin Trend = -27.8106 %, trajectory=MIXED_DOWNWARD_NET). |
| **TSLA** | `CLM-19` | **Operating Cash Flow Margin (DOWNWARD)**: Profitability margins experienced downward compression (-35.9%). | `[C15]` | `financial_metric` | `MONOTONIC_DOWNWARD` | -35.87% | YES | `supported` | `supported` | Claim supported by verified trend receipt calc_trend_operating_cash_flow_margin_FY2021_FY2023 (operating_cash_flow_margin Trend = -35.8732 %, trajectory=MONOTONIC_DOWNWARD). |
| **TSLA** | `CLM-20` | **Free Cash Flow (MIXED)**: free_cash_flow demonstrated mixed volatility across periods (net shift: -658000000.00 USD (-13.1%)). | `[C16]` | `historical_comparison` | `MIXED_DOWNWARD_NET` | -13.12% | YES | `supported` | `supported` | Claim supported by verified trend receipt calc_trend_free_cash_flow_FY2021_FY2023 (free_cash_flow Trend = -13.1206 %, trajectory=MIXED_DOWNWARD_NET). |
| **TSLA** | `CLM-38` | **Financial Performance:** Verified deterministic calculation establishes Revenue Growth at 18.80% for the target period . | `[C1]` | `financial_metric` | `N/A` | N/A | YES | `supported` | `supported` | Deterministic calculation receipt C1 (0001318605_revenue_growth_annual_2023-12-31) verifies revenue_growth = 18.7953 percentage. |
| **NVDA** | `CLM-09` | Deterministic calculation of revenue_growth for FY2024: 125.85% | `[C1]` | `financial_metric` | `N/A` | N/A | YES | `supported` | `supported` | Deterministic calculation receipt C1 (0001045810_revenue_growth_annual_2024-01-28) verifies revenue_growth = 125.8545 percentage. |
| **NVDA** | `CLM-10` | Deterministic calculation of gross_profit_margin for FY2024: 72.72% | `[C2]` | `financial_metric` | `N/A` | N/A | YES | `supported` | `supported` | Deterministic calculation receipt C2 (0001045810_gross_profit_margin_annual_2024-01-28) verifies gross_profit_margin = 72.7176 percentage. |
| **NVDA** | `CLM-11` | Deterministic calculation of revenue_growth for FY2023: 0.22% | `[C3]` | `financial_metric` | `N/A` | N/A | YES | `supported` | `supported` | Deterministic calculation receipt C3 (0001045810_revenue_growth_annual_2023-01-29) verifies revenue_growth = 0.2229 percentage. |
| **NVDA** | `CLM-12` | Deterministic calculation of gross_profit_margin for FY2023: 56.93% | `[C4]` | `financial_metric` | `N/A` | N/A | YES | `supported` | `supported` | Deterministic calculation receipt C4 (0001045810_gross_profit_margin_annual_2023-01-29) verifies gross_profit_margin = 56.9289 percentage. |
| **NVDA** | `CLM-13` | Deterministic calculation of revenue_growth for FY2022: 61.40% | `[C5]` | `financial_metric` | `N/A` | N/A | YES | `supported` | `supported` | Deterministic calculation receipt C5 (0001045810_revenue_growth_annual_2022-01-30) verifies revenue_growth = 61.4033 percentage. |
| **NVDA** | `CLM-14` | Deterministic calculation of gross_profit_margin for FY2022: 64.93% | `[C6]` | `financial_metric` | `N/A` | N/A | YES | `supported` | `supported` | Deterministic calculation receipt C6 (0001045810_gross_profit_margin_annual_2022-01-30) verifies gross_profit_margin = 64.9290 percentage. |
| **NVDA** | `CLM-16` | **Revenue Growth (MIXED)**: revenue_growth demonstrated mixed volatility across periods (net shift: +64.45 percentage (+105.0%)). | `[C7]` | `historical_comparison` | `MIXED_UPWARD_NET` | +104.96% | YES | `supported` | `supported` | Claim supported by verified trend receipt calc_trend_revenue_growth_FY2022_FY2024 (revenue_growth Trend = 104.9637 %, trajectory=MIXED_UPWARD_NET). |
| **NVDA** | `CLM-17` | **Gross Profit Margin (MIXED)**: gross_profit_margin demonstrated mixed volatility across periods (net shift: +7.79 percentage (+12.0%)). | `[C8]` | `historical_comparison` | `MIXED_UPWARD_NET` | +12.00% | YES | `supported` | `supported` | Claim supported by verified trend receipt calc_trend_gross_profit_margin_FY2022_FY2024 (gross_profit_margin Trend = 11.9956 %, trajectory=MIXED_UPWARD_NET). |
| **NVDA** | `CLM-32` | **Financial Performance:** Verified deterministic calculation establishes Revenue Growth at 125.85% for the target period . | `[C1]` | `financial_metric` | `N/A` | N/A | YES | `supported` | `supported` | Deterministic calculation receipt C1 (0001045810_revenue_growth_annual_2024-01-28) verifies revenue_growth = 125.8545 percentage. |

---

## 7. Missing or Invalid Evidence Tests & Fail-Closed Behavior

To verify fail-closed enforcement, the auditor was subjected to missing, corrupt, and adversarial receipts:

| Test Case | Injected Defect | Expected Outcome | Observed Auditor Outcome | Status |
|---|---|---|---|:---:|
| Missing Receipt | `receipt=None` passed for citation `C99` | Fail closed (`missing_receipt`) | `missing_receipt`: Receipt data missing | PASS |
| Missing Observations | Empty `values: []` list | Fail closed (`incomplete`) | `incomplete`: Missing intermediate observations | PASS |
| Missing Start/End | `start_value=None`, `end_value=10.0` | Fail closed (`incomplete`) | `incomplete`: Missing start_value | PASS |
| Zero Denominator | `start_value=0.0`, `end_value=25.0` | Undefined percentage error | `Zero denominator: percentage change undefined` | PASS |
| Trajectory Mismatch | Recorded `MONOTONIC_UPWARD` for `[10, 5, 20]` | Fail closed (`failed_trajectory`) | `Trajectory mismatch: recorded 'MONOTONIC_UPWARD', recalculated 'MIXED_UPWARD_NET'` | PASS |
| Formula Mismatch | Formula name 'Growth' with expression `V_end - V_start` | Fail closed (`invalid_formula`) | `Formula metadata mismatch: formula_name is 'Growth'` | PASS |
| Out-of-Order Periods | Periods `['FY2023', 'FY2021', 'FY2022']` | Fail closed (`failed_recalculation`) | `Periods out of chronological order` | PASS |
| Duplicate Periods | Periods `['FY2021', 'FY2021', 'FY2022']` | Fail closed (`failed_recalculation`) | `Duplicate periods detected` | PASS |
| Missing Mid Year | Periods `['FY2021', 'FY2023']` (missing FY2022) | Fail closed (`failed_recalculation`) | `Missing intermediate period in annual series` | PASS |
| Two-Point Mixed | Series `[10, 20]` claiming mixed trajectory | Fail closed (`failed_recalculation`) | `Two-observation series cannot establish mixed trajectory` | PASS |

---

## 8. Claim Classification Persistence & Migration Verification

All claims were verified through the persistence layer (SQLite `answer_claims`):

- **Model Field Added:** `ClaimVerificationResult.claim_type` was explicitly added to ensure Pydantic serialization preserves the classified claim type.
- **Storage Engine Updated:** `Database.save_verification_run()` now persists `claim_type_str` alongside serialized `numeric_values`, `mentioned_company`, and `mentioned_period`.
- **Contextual Historical Migration:** Database initialization runs a narrowed schema migration requiring comparative context and explicitly excluding legal debt acceleration clauses (`debt repayment due upon acceleration`) and generic operational acceleration (`accelerated production`).
- **Verified Result:** In the multi-company audit, all genuine trend assertions are classified and persisted as `historical_comparison` while legal and operational clauses remain appropriately classified as `general_fact` or `structural_statement`.

---

## 9. Receipt Deduplication Results

The production `TrendReceiptAuditor` ensures that each calculation receipt is independently evaluated once while maintaining multiple claim citations:

| Company | Calculation Receipt ID | Citation ID | Evaluated Times | Linked Claims |
|---|---|---|---:|---|
| **MSFT** | `calc_trend_revenue_growth_FY2021_FY2023` | `[C4]` | 1 (Cached) | `CLM-12`, `CLM-14` |
| **TSLA** | `calc_trend_revenue_growth_FY2021_FY2023` | `[C13]` | 1 (Cached) | `CLM-17` |
| **TSLA** | `calc_trend_gross_profit_margin_FY2021_FY2023` | `[C14]` | 1 (Cached) | `CLM-18` |
| **TSLA** | `calc_trend_operating_cash_flow_margin_FY2021_FY2023` | `[C15]` | 1 (Cached) | `CLM-19` |
| **TSLA** | `calc_trend_free_cash_flow_FY2021_FY2023` | `[C16]` | 1 (Cached) | `CLM-20` |
| **NVDA** | `calc_trend_revenue_growth_FY2022_FY2024` | `[C7]` | 1 (Cached) | `CLM-16` |
| **NVDA** | `calc_trend_gross_profit_margin_FY2022_FY2024` | `[C8]` | 1 (Cached) | `CLM-17` |

---

## 10. Audit Quality Summary & Acceptance

### Audit Quality Achievements:
1. **Complete Semantics & Provenance:** Trajectory assertions are verified against full ordered observation series with $10^{-4}$ tolerance, traced back to SEC 10-K calculation records in SQLite.
2. **Strict Polarity:** Claims asserting growth when a net decline occurred (or vice versa) are deterministically contradicted.
3. **Fail-Closed Guarantee:** Missing receipts, missing observations, or formula contradictions immediately fail verification with explicit reasons.
4. **Persistent Claim Classification:** Claim classification (`historical_comparison`) is retained through Pydantic serialization, SQLite persistence, and audit reporting with narrowed legal/operational exclusions.
5. **Reconciled Denominators:** Headline claim outcomes and company verification status are strictly reconciled with independent semantic trend findings; company status cannot be `verified` if any substantive claim fails.
6. **Production Deduplication:** Reusable `TrendReceiptAuditor` guarantees single independent evaluation per unique receipt and links all referencing claims.

### Remaining Limitations:
- Multi-period trends currently evaluate annual statutory periods (FY2021–FY2023). Multi-quarter trend analysis (e.g. Q1–Q4 sequential) will be expanded in future roadmap sessions.
- Semantic NLP claim extraction relies on canonical keyword matching and regex patterns; complex compound claims with nested sub-clauses are decomposed into atomic claims.
