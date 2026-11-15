# Finova AI — SEC EDGAR Data Ingestion & Retrieval Pipeline

## 1. Overview & Architecture

The Finova AI SEC Data Pipeline is engineered to ingest, normalize, and persist corporate financial facts from official SEC EDGAR endpoints in compliance with SEC fair-access policies.

```mermaid
flowchart TD
    UserQuery(["Ticker / CIK Query\n(e.g., AAPL)"]) --> CompService["CompanyService\nTicker & CIK Resolution"]
    CompService -->|Local Cache Hit| MemoryDir["In-Memory Ticker Directory"]
    CompService -->|Cache Miss / TTL| SECTickers["SEC EDGAR\ncompany_tickers.json"]
    
    CompService --> CIKIdent["Normalized 10-Digit CIK\n(e.g., 0000320193)"]
    
    CIKIdent --> SECClientEngine["SECClient Engine\nRate-Limited & Backoff Retries"]
    
    SECClientEngine -->|GET submissions| Submissions["SEC Submissions API\nMetadata & Form Filings"]
    SECClientEngine -->|GET companyfacts| Facts["SEC Company Facts API\nUS-GAAP XBRL Taxonomy"]
    
    Submissions --> FilingParser["Filing Flattener & Direct Archive Linker"]
    Facts --> Extractor["FinancialExtractor\nCanonical Metric Mapper"]
    
    Extractor --> Normalizer["DataNormalizer\nPeriod Typing & Deduplication"]
    Normalizer --> Observations["Canonical FinancialObservation Stream"]
    
    FilingParser --> SQLite["SQLite Relational Storage\n(companies, filings, observations)"]
    Observations --> SQLite
    
    SQLite --> FastAPIRoutes["FastAPI REST Endpoints\n/api/v1/companies/*"]
    FastAPIRoutes --> StreamlitUI["Streamlit Frontend & Downstream Multi-Agent RAG"]
```

---

## 2. SEC Compliance & Fair Access Protocol

To comply with the US Securities and Exchange Commission's automated access guidelines:
1. **Declared User-Agent**: Programmatic requests must transmit a declared User-Agent containing the application name and contact email in the header:
   ```http
   User-Agent: FinovaAI-Research/0.1.0 (contact@example.com)
   Accept-Encoding: gzip, deflate
   ```
   If the configured User-Agent lacks an email address or is missing, `SECClient` raises a `SECConfigurationError` prior to dispatching any network calls.
2. **Rate Limiting**: Request dispatching is throttled to $\le 8$ requests per second (well within the SEC's 10 req/sec threshold) using monotonic interval tracking.
3. **Exponential Backoff**: Transient errors (HTTP 429 Too Many Requests or 5xx server issues) trigger exponential backoff retry cycles ($0.5 \text{s} \times 2^{\text{attempt}}$).

---

## 3. Supported Financial Metrics

Finova AI extracts standard US-GAAP taxonomy elements and maps them into canonical financial concepts:

### Income Statement
| Canonical Metric | Statement | Primary US-GAAP XBRL Tag | Fallback Alternative Tags |
| :--- | :--- | :--- | :--- |
| **Revenue** | Income Statement | `RevenueFromContractWithCustomerExcludingAssessedTax` | `Revenues`, `SalesRevenueNet`, `SalesRevenueGoodsNet` |
| **Cost of Revenue** | Income Statement | `CostOfGoodsAndServicesSold` | `CostOfRevenue`, `CostOfGoodsSold` |
| **Gross Profit** | Income Statement | `GrossProfit` | — |
| **Operating Income** | Income Statement | `OperatingIncomeLoss` | — |
| **Net Income** | Income Statement | `NetIncomeLoss` | `ProfitLoss` |
| **Earnings Per Share** | Income Statement | `EarningsPerShareDiluted` | `EarningsPerShareBasic` |

### Balance Sheet (Instant Point-in-Time)
| Canonical Metric | Statement | Primary US-GAAP XBRL Tag | Fallback Alternative Tags |
| :--- | :--- | :--- | :--- |
| **Total Assets** | Balance Sheet | `Assets` | — |
| **Current Assets** | Balance Sheet | `AssetsCurrent` | — |
| **Total Liabilities** | Balance Sheet | `Liabilities` | — |
| **Current Liabilities** | Balance Sheet | `LiabilitiesCurrent` | — |
| **Stockholders' Equity** | Balance Sheet | `StockholdersEquity` | `CommonStockholdersEquity` |
| **Cash and Cash Equivalents** | Balance Sheet | `CashAndCashEquivalentsAtCarryingValue` | `CashCashEquivalentsRestrictedCash...` |
| **Long-Term Debt** | Balance Sheet | `LongTermDebtNoncurrent` | `LongTermDebt` |

### Cash Flow Statement
| Canonical Metric | Statement | Primary US-GAAP XBRL Tag | Fallback Alternative Tags |
| :--- | :--- | :--- | :--- |
| **Operating Cash Flow** | Cash Flow Statement | `NetCashProvidedByUsedInOperatingActivities` | — |
| **Investing Cash Flow** | Cash Flow Statement | `NetCashProvidedByUsedInInvestingActivities` | — |
| **Financing Cash Flow** | Cash Flow Statement | `NetCashProvidedByUsedInFinancingActivities` | — |
| **Capital Expenditures** | Cash Flow Statement | `PaymentsToAcquirePropertyPlantAndEquipment` | `PaymentsToAcquireProductiveAssets` |

---

## 4. Period Typing & Normalization Methodology

A recurring source of error in financial LLM tools is confusing cumulative Year-to-Date (YTD) numbers with standalone quarterly metrics.

Finova AI classifies every incoming XBRL fact into one of four deterministic temporal regimes:
- **`instant`**: Point-in-time Balance Sheet figures (no start date, only end date).
- **`annual`**: Full-year flow figures spanning between 330 and 390 days, or matching form `10-K` with fiscal period `FY`.
- **`quarterly`**: Discrete three-month periods spanning between 60 and 115 days (standalone Q1, Q2, Q3, Q4).
- **`ytd`**: Cumulative multi-quarter periods reported in 10-Q disclosures spanning 150 to 310 days (e.g., 6-month Q1+Q2 or 9-month Q1+Q2+Q3).

### Deduplication & Amendment Handling
Corporate filers regularly restate figures or submit amended filings (`10-K/A`, `10-Q/A`). When duplicate observations are encountered for the composite key:
```
(company_cik, metric_name, period_end, period_type, period_start)
```
Finova AI selects the observation with the most recent `filing_date`, ensuring that amended figures cleanly supersede obsolete disclosures.

---

## 5. Relational Database Schema (SQLite)

```mermaid
erDiagram
    COMPANIES ||--o{ FILINGS : "submits"
    COMPANIES ||--o{ FINANCIAL_OBSERVATIONS : "reports"
    FILINGS ||--o{ FINANCIAL_OBSERVATIONS : "contains"

    COMPANIES {
        string cik PK "10-digit zero-padded CIK"
        string ticker UK "Normalized stock ticker"
        string name "Official corporate title"
        string sic "Standard Industrial Classification"
        string sic_description "Industry sector"
        string fiscal_year_end "Fiscal year end date (MMDD)"
        string state_location "Headquarters state/jurisdiction"
        string updated_at "ISO-8601 UTC timestamp"
    }

    FILINGS {
        string accession_number PK "SEC EDGAR accession number"
        string cik FK "Company CIK"
        string form "Form code (10-K, 10-Q, 8-K)"
        string filing_date "Date accepted by SEC"
        string report_date "Period end date"
        string acceptance_date "Timestamp of acceptance"
        string primary_document "Primary HTML/XBRL file name"
        string primary_doc_description "Document description"
        int is_xbrl "1 if XBRL data attached, else 0"
        int is_inline_xbrl "1 if iXBRL, else 0"
        string url "Canonical SEC archive hyperlink"
        string created_at "ISO-8601 UTC timestamp"
    }

    FINANCIAL_OBSERVATIONS {
        int id PK "Autoincrementing ID"
        string cik FK "Company CIK"
        string ticker "Stock ticker"
        string company_name "Corporate title"
        string metric_name "Canonical concept name"
        string statement_type "Income, Balance Sheet, Cash Flow"
        string original_tag "Raw US-GAAP XBRL tag"
        real numeric_value "Numerical value"
        string unit "USD, shares, pure"
        string period_start "Start date or empty string"
        string period_end "Period end date"
        int duration_days "Days elapsed"
        string period_type "annual, quarterly, ytd, instant"
        int fiscal_year "Fiscal year"
        string fiscal_period "FY, Q1, Q2, Q3"
        string filing_date "Filing date"
        string filing_type "10-K, 10-Q"
        string accession_number "SEC accession number"
        string source_url "Filing directory hyperlink"
        string created_at "ISO-8601 UTC timestamp"
    }
```
