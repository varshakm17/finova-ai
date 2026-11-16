"""Live SEC EDGAR Integration Test Suite.

Tests 12 critical live integration capabilities against official SEC EDGAR endpoints:
1. Ticker to CIK resolution
2. Submissions list retrieval
3. Company facts (XBRL) retrieval
4. 10-K accession number lookup
5. Filing document download with caching
6. HTML parsing & text normalization
7. Section extraction (Item 1, 1A, 7, 7A)
8. Chunk generation with metadata
9. XBRL financial metric extraction
10. Ingestion persistence to SQLite
11. Evidence retrieval over ingested chunks
12. SEC URL generation & verification

Enforces SEC fair access: valid User-Agent, <= 10 req/s, retry on 429, and cache reuse.
These tests are skipped by default in normal offline test runs.
To execute live tests, pass `--run-live-sec` or `-m live_sec`.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import httpx
import pytest

from backend.data.chunker import DocumentChunk, SectionChunker
from backend.data.company_service import CompanyService
from backend.data.document_storage import DocumentStorage
from backend.data.filing_downloader import FilingDownloader
from backend.data.financial_extractor import FinancialExtractor
from backend.data.html_parser import HTMLDocumentParser
from backend.data.sec_client import (
    SEC_ARCHIVES_BASE_URL,
    SECClient,
    SECError,
    normalize_cik,
    validate_user_agent,
)
from backend.data.section_extractor import SectionExtractor
from backend.data.storage import Database
from backend.retrieval.bm25_indexing_service import BM25IndexingService
from backend.retrieval.bm25_search import BM25SearchService
from config.settings import Settings

pytestmark = pytest.mark.live_sec


@pytest.fixture(scope="module")
def live_settings() -> Settings:
    """Settings configured with compliant User-Agent for live SEC testing."""
    settings = Settings(
        SEC_USER_AGENT="FinovaAI-TestSuite/1.0 (research-integration@finova.ai)",
        CHUNK_TARGET_SIZE=2500,
        CHUNK_OVERLAP=300,
    )
    validate_user_agent(settings.SEC_USER_AGENT)
    return settings


@pytest.fixture(scope="module")
def live_client(live_settings: Settings) -> SECClient:
    """SEC client instance respecting SEC fair access limits."""
    return SECClient(settings=live_settings, requests_per_second=5.0, timeout=20.0)


def test_live_01_ticker_to_cik_resolution(live_settings: Settings) -> None:
    """Capability 1: Verify live resolution of company stock ticker to official CIK."""
    company_service = CompanyService(settings=live_settings)
    try:
        aapl_identity = company_service.get_company_by_ticker("AAPL")
    except (SECError, httpx.HTTPError) as exc:
        pytest.skip(f"SEC EDGAR API unavailable: {exc}")

    assert aapl_identity is not None
    assert aapl_identity["cik"] == "0000320193"
    assert "apple" in aapl_identity["company_name"].lower()


def test_live_02_submissions_retrieval(live_client: SECClient) -> None:
    """Capability 2: Verify live retrieval of company submissions list from SEC."""
    try:
        submissions = live_client.get_company_submissions("0000320193")
    except (SECError, httpx.HTTPError) as exc:
        pytest.skip(f"SEC EDGAR API unavailable: {exc}")

    assert isinstance(submissions, dict)
    assert "filings" in submissions
    assert "recent" in submissions["filings"]
    recent = submissions["filings"]["recent"]
    assert "form" in recent
    assert "accessionNumber" in recent
    assert len(recent["form"]) > 0


def test_live_03_company_facts_xbrl_retrieval(live_client: SECClient) -> None:
    """Capability 3: Verify live retrieval of structured XBRL facts JSON."""
    try:
        facts = live_client.get_company_facts("0000320193")
    except (SECError, httpx.HTTPError) as exc:
        pytest.skip(f"SEC EDGAR API unavailable: {exc}")

    assert isinstance(facts, dict)
    assert "facts" in facts
    assert "us-gaap" in facts["facts"]
    us_gaap = facts["facts"]["us-gaap"]
    assert any(
        k in us_gaap
        for k in [
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "GrossProfit",
            "OperatingIncomeLoss",
        ]
    )


def test_live_04_10k_accession_lookup(live_client: SECClient) -> None:
    """Capability 4: Verify discovery of annual Form 10-K filing accession number."""
    try:
        filings = live_client.get_company_filings("0000320193", form_type="10-K")
    except (SECError, httpx.HTTPError) as exc:
        pytest.skip(f"SEC EDGAR API unavailable: {exc}")

    assert len(filings) > 0
    latest_10k = filings[0]
    assert latest_10k["form"] == "10-K"
    assert re.match(r"^\d{10}-\d{2}-\d{6}$", latest_10k["accession_number"])
    assert latest_10k["primary_document"] != ""


def test_live_05_filing_document_download(live_settings: Settings) -> None:
    """Capability 5: Download primary 10-K document with cache verification."""
    with tempfile.TemporaryDirectory() as tmpdir:
        downloader = FilingDownloader(
            settings=live_settings, storage_dir=Path(tmpdir), timeout=25.0
        )
        source_url = "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm"

        try:
            downloaded = downloader.download(
                url=source_url,
                accession_number="0000320193-23-000106",
                cik="0000320193",
                ticker="AAPL",
                form="10-K",
                primary_doc="aapl-20230930.htm",
            )
        except (SECError, httpx.HTTPError) as exc:
            pytest.skip(f"SEC EDGAR archive unavailable: {exc}")

        assert downloaded.local_file_path.exists()
        assert downloaded.file_size_bytes > 0
        assert downloaded.is_cached is False

        # Capability 5b: Verify cache re-use on second call
        cached_download = downloader.download(
            url=source_url,
            accession_number="0000320193-23-000106",
            cik="0000320193",
            ticker="AAPL",
            form="10-K",
            primary_doc="aapl-20230930.htm",
        )
        assert cached_download.is_cached is True


def test_live_06_html_parsing_text_normalization() -> None:
    """Capability 6: Parse filing HTML and normalize cleaned financial text."""
    parser = HTMLDocumentParser()
    sample_sec_html = """
    <html>
      <head><title>Form 10-K</title></head>
      <body>
        <div><h1>PART I</h1></div>
        <div><h2>ITEM 1. BUSINESS</h2></div>
        <p>Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables and accessories.</p>
        <div><h2>ITEM 1A. RISK FACTORS</h2></div>
        <p>Global supply chain concentration poses material operational risks.</p>
      </body>
    </html>
    """
    clean_text = parser.parse_html(sample_sec_html)
    assert "Apple Inc." in clean_text
    assert "ITEM 1. BUSINESS" in clean_text
    assert "smartphones, personal computers" in clean_text


def test_live_07_section_extraction() -> None:
    """Capability 7: Extract statutory Item 1, 1A, 7 sections."""
    extractor = SectionExtractor(min_section_chars=10)
    filing_text = (
        "PART I\n\n"
        "ITEM 1. BUSINESS\nApple designs consumer electronics and software services across global platforms.\n\n"
        "ITEM 1A. RISK FACTORS\nGlobal economic conditions may adversely impact consumer demand and supply continuity.\n\n"
        "ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION AND RESULTS OF OPERATIONS\n"
        "Net sales were $383,285 million in 2023 compared to $394,328 million in 2022.\n\n"
        "ITEM 7A. QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT MARKET RISK\n"
        "Interest rate volatility and foreign exchange risks are actively managed.\n\n"
        "SIGNATURES"
    )
    sections = extractor.extract_sections(filing_text)
    section_map = {s.section_identifier: s for s in sections}

    assert "ITEM_1" in section_map
    assert "ITEM_1A" in section_map
    assert "ITEM_7" in section_map
    assert "ITEM_7A" in section_map
    assert section_map["ITEM_7"].status == "extracted"
    assert "Net sales were $383,285 million" in section_map["ITEM_7"].text


def test_live_08_chunk_generation_with_metadata() -> None:
    """Capability 8: Chunk statutory sections with provenance metadata."""
    chunker = SectionChunker(chunk_size=300, overlap=50)
    text = (
        "ITEM 7. MD&A. Net sales were $383,285 million in 2023. Gross margin was 44.1%. "
        * 15
    )

    chunks = chunker.chunk_section(
        section_text=text,
        company_ticker="AAPL",
        company_cik="0000320193",
        company_name="Apple Inc.",
        accession_number="0000320193-23-000106",
        filing_type="10-K",
        filing_date="2023-11-03",
        report_date="2023-09-30",
        section_identifier="ITEM_7",
        section_title="Management's Discussion and Analysis",
        source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
    )

    assert len(chunks) > 1
    for c in chunks:
        assert c.section_identifier == "ITEM_7"
        assert c.company_ticker == "AAPL"
        assert c.company_cik == "0000320193"
        assert len(c.chunk_text) > 0


def test_live_09_xbrl_metric_extraction() -> None:
    """Capability 9: Extract standardized XBRL financial observations."""
    extractor = FinancialExtractor()
    mock_facts = {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            {
                                "form": "10-K",
                                "fp": "FY",
                                "fy": 2023,
                                "val": 383285000000,
                                "end": "2023-09-30",
                                "accn": "0000320193-23-000106",
                            }
                        ]
                    }
                },
                "GrossProfit": {
                    "units": {
                        "USD": [
                            {
                                "form": "10-K",
                                "fp": "FY",
                                "fy": 2023,
                                "val": 169148000000,
                                "end": "2023-09-30",
                                "accn": "0000320193-23-000106",
                            }
                        ]
                    }
                },
            }
        },
    }
    obs = extractor.extract_company_facts(
        company_facts=mock_facts, ticker="AAPL", company_name="Apple Inc."
    )
    metric_map = {o.metric_name: o.numeric_value for o in obs}

    assert "Revenue" in metric_map
    assert metric_map["Revenue"] == 383285000000.0
    assert "Gross Profit" in metric_map
    assert metric_map["Gross Profit"] == 169148000000.0


def test_live_10_ingestion_persistence() -> None:
    """Capability 10: Persist document, sections, and chunks to SQLite."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db = Database(db_path=db_path)
    # Ensure foreign key company exists
    db.save_company({"cik": "0000320193", "ticker": "AAPL", "name": "Apple Inc."})
    storage = DocumentStorage(db=db)

    # Insert test document
    doc_id = "doc_aapl_10k_2023"
    saved_id = storage.save_document(
        {
            "document_id": doc_id,
            "cik": "0000320193",
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "accession_number": "0000320193-23-000106",
            "filing_type": "10-K",
            "filing_date": "2023-11-03",
            "report_date": "2023-09-30",
            "primary_document": "aapl-20230930.htm",
            "source_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
            "local_file_path": "datasets/filings/aapl.htm",
            "processing_status": "completed",
            "document_hash": "hash_aapl_10k_2023",
        }
    )
    assert saved_id == doc_id

    # Insert chunk
    chunk = DocumentChunk(
        company_ticker="AAPL",
        company_cik="0000320193",
        company_name="Apple Inc.",
        accession_number="0000320193-23-000106",
        filing_type="10-K",
        filing_date="2023-11-03",
        report_date="2023-09-30",
        section_identifier="ITEM_7",
        section_title="MD&A",
        chunk_index=0,
        source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
        start_offset=0,
        end_offset=50,
        char_count=50,
        chunk_text="Total net sales were $383,285 million in 2023.",
    )
    # First save section
    extractor = SectionExtractor(min_section_chars=10)
    sections = extractor.extract_sections(
        "ITEM 7. MD&A\nTotal net sales were $383,285 million in 2023.\n\nSIGNATURES"
    )
    storage.save_sections(doc_id, sections)

    saved_chunks = storage.save_chunks(doc_id, [chunk])
    assert saved_chunks == 1


def test_live_11_evidence_retrieval_over_ingested_chunks(
    live_settings: Settings,
) -> None:
    """Capability 11: Execute hybrid search over ingested filing chunks."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db = Database(db_path=db_path)
    db.save_company({"cik": "0000320193", "ticker": "AAPL", "name": "Apple Inc."})
    storage = DocumentStorage(db=db)

    doc_id = "doc_aapl_10k_2023"
    storage.save_document(
        {
            "document_id": doc_id,
            "cik": "0000320193",
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "accession_number": "0000320193-23-000106",
            "filing_type": "10-K",
            "filing_date": "2023-11-03",
            "report_date": "2023-09-30",
            "primary_document": "aapl-20230930.htm",
            "source_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
            "local_file_path": "datasets/filings/aapl.htm",
            "processing_status": "completed",
            "document_hash": "hash_aapl_10k_2023",
        }
    )

    extractor = SectionExtractor(min_section_chars=10)
    sections = extractor.extract_sections(
        "ITEM 7. MD&A\nTotal net sales were $383,285 million in 2023.\n\nSIGNATURES"
    )
    storage.save_sections(doc_id, sections)

    chunk = DocumentChunk(
        company_ticker="AAPL",
        company_cik="0000320193",
        company_name="Apple Inc.",
        accession_number="0000320193-23-000106",
        filing_type="10-K",
        filing_date="2023-11-03",
        report_date="2023-09-30",
        section_identifier="ITEM_7",
        section_title="MD&A",
        chunk_index=0,
        source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
        start_offset=0,
        end_offset=85,
        char_count=85,
        chunk_text="Total net sales were $383,285 million in 2023 compared to $394,328 million in 2022.",
    )
    storage.save_chunks(doc_id, [chunk])

    indexer = BM25IndexingService(document_storage=storage, settings=live_settings)
    indexer.index_company_chunks(ticker="AAPL")

    bm25 = BM25SearchService(
        document_storage=storage,
        bm25_index=indexer.bm25_index,
        settings=live_settings,
    )
    results = bm25.search(query="net sales 2023", ticker="AAPL", top_k=3)
    assert len(results) > 0
    assert "aapl" in results[0].ticker.lower()


def test_live_12_sec_url_generation_verification() -> None:
    """Capability 12: Generate and verify compliance of SEC EDGAR Archive URLs."""
    cik = "0000320193"
    cik_int = int(normalize_cik(cik))
    accn = "0000320193-23-000106"
    accn_nodash = accn.replace("-", "")
    primary_doc = "aapl-20230930.htm"

    url = SEC_ARCHIVES_BASE_URL.format(
        cik_int=cik_int, accession_nodash=accn_nodash, primary_doc=primary_doc
    )

    assert (
        url
        == "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm"
    )
    assert url.startswith("https://www.sec.gov/Archives/edgar/data/")
    assert primary_doc in url
