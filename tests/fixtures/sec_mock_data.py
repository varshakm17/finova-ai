"""Mock data fixtures representing official SEC EDGAR responses."""

MOCK_TICKERS_PAYLOAD = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"},
    "2": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    "3": {"cik_str": 1067983, "ticker": "BRK-B", "title": "BERKSHIRE HATHAWAY INC"},
}

MOCK_SUBMISSIONS_PAYLOAD = {
    "cik": "0000320193",
    "entityType": "operating",
    "sic": "3571",
    "sicDescription": "Electronic Computers",
    "name": "Apple Inc.",
    "tickers": ["AAPL"],
    "exchanges": ["Nasdaq"],
    "fiscalYearEnd": "0930",
    "stateOfIncorporation": "CA",
    "filings": {
        "recent": {
            "accessionNumber": [
                "0000320193-23-000106",
                "0000320193-23-000077",
                "0000320193-23-000050",
            ],
            "filingDate": ["2023-11-03", "2023-08-04", "2023-05-05"],
            "reportDate": ["2023-09-30", "2023-07-01", "2023-04-01"],
            "acceptanceDateTime": [
                "2023-11-03T18:04:12.000Z",
                "2023-08-04T18:01:05.000Z",
                "2023-05-05T18:02:40.000Z",
            ],
            "form": ["10-K", "10-Q", "10-Q"],
            "primaryDocument": [
                "aapl-20230930.htm",
                "aapl-20230701.htm",
                "aapl-20230401.htm",
            ],
            "primaryDocDescription": [
                "10-K ANNUAL REPORT",
                "10-Q QUARTERLY REPORT",
                "10-Q QUARTERLY REPORT",
            ],
            "isXBRL": [1, 1, 1],
            "isInlineXBRL": [1, 1, 1],
        }
    },
}

MOCK_COMPANY_FACTS_PAYLOAD = {
    "cik": 320193,
    "entityName": "Apple Inc.",
    "facts": {
        "us-gaap": {
            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                "label": "Revenue",
                "description": "Total revenue...",
                "units": {
                    "USD": [
                        # Annual FY2023
                        {
                            "start": "2022-10-01",
                            "end": "2023-09-30",
                            "val": 383285000000,
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                            "accn": "0000320193-23-000106",
                        },
                        # Standalone Q3
                        {
                            "start": "2023-04-02",
                            "end": "2023-07-01",
                            "val": 81797000000,
                            "fy": 2023,
                            "fp": "Q3",
                            "form": "10-Q",
                            "filed": "2023-08-04",
                            "accn": "0000320193-23-000077",
                        },
                        # Year-To-Date (9 Months) - should be classified as YTD
                        {
                            "start": "2022-10-01",
                            "end": "2023-07-01",
                            "val": 293787000000,
                            "fy": 2023,
                            "fp": "Q3",
                            "form": "10-Q",
                            "filed": "2023-08-04",
                            "accn": "0000320193-23-000077",
                        },
                    ]
                },
            },
            "Assets": {
                "label": "Assets",
                "description": "Total assets...",
                "units": {
                    "USD": [
                        {
                            "end": "2023-09-30",
                            "val": 352583000000,
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                            "accn": "0000320193-23-000106",
                        }
                    ]
                },
            },
            "OperatingIncomeLoss": {
                "label": "Operating Income",
                "units": {
                    "USD": [
                        {
                            "start": "2022-10-01",
                            "end": "2023-09-30",
                            "val": 114301000000,
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                            "accn": "0000320193-23-000106",
                        }
                    ]
                },
            },
            "NetIncomeLoss": {
                "label": "Net Income",
                "units": {
                    "USD": [
                        {
                            "start": "2022-10-01",
                            "end": "2023-09-30",
                            "val": 96995000000,
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                            "accn": "0000320193-23-000106",
                        }
                    ]
                },
            },
            "NetCashProvidedByUsedInOperatingActivities": {
                "label": "Operating Cash Flow",
                "units": {
                    "USD": [
                        {
                            "start": "2022-10-01",
                            "end": "2023-09-30",
                            "val": 110543000000,
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                            "accn": "0000320193-23-000106",
                        }
                    ]
                },
            },
            "PaymentsToAcquirePropertyPlantAndEquipment": {
                "label": "Capital Expenditures",
                "units": {
                    "USD": [
                        {
                            "start": "2022-10-01",
                            "end": "2023-09-30",
                            "val": 10959000000,
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                            "accn": "0000320193-23-000106",
                        }
                    ]
                },
            },
        }
    },
}
