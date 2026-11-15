# Datasets Directory

This directory is designated for holding local financial datasets, SEC filings, caches, and evaluation benchmark files used by Finova AI.

## Directory Structure (Planned)

```
datasets/
├── cache/            # Local cache for downloaded SEC EDGAR filings (XBRL, JSON, HTML)
├── raw/              # Raw company reports (10-K, 10-Q)
├── processed/        # Extracted structured financial metrics and normalized tables
└── benchmarks/       # Golden standard QA pairs and ground-truth financial metrics for evaluation
```

## Guidelines

- **Do NOT commit raw filing data or large cache files to version control.** The `.gitignore` is configured to exclude `datasets/cache/` and `datasets/raw/`.
- Downloaded SEC filings will be retrieved on-demand and cached locally during future sessions.
- Ground truth benchmarks and sample schemas for testing should be stored in `datasets/benchmarks/` with reproducible generation scripts.

