"""Research tools for SEC EDGAR retrieval and evidence extraction."""

from __future__ import annotations

from typing import Any

from backend.retrieval.hybrid_search import HybridSearchService
from backend.utils.logger import get_logger

logger = get_logger("research_tools")


def hybrid_search_tool(
    query: str,
    ticker: str | None = None,
    top_k: int = 5,
    search_service: HybridSearchService | None = None,
) -> list[dict[str, Any]]:
    """Execute hybrid dense and sparse search over ingested SEC filings.

    Args:
        query: Search question or keywords.
        ticker: Optional company stock ticker filter.
        top_k: Number of results to retrieve.
        search_service: Optional service instance.

    Returns:
        List of candidate chunk dictionaries.
    """
    service = search_service or HybridSearchService()
    try:
        resp = service.search(query=query, ticker=ticker, top_k=top_k)
        return [r.model_dump() for r in resp.results]
    except Exception as exc:  # noqa: BLE001
        logger.error("hybrid_search_tool failed: %s", exc)
        return []
