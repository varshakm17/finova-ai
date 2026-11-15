"""RAG Module for Finova AI — Evidence-Grounded Financial Intelligence."""

from backend.rag.citation_validator import CitationValidationResult, CitationValidator
from backend.rag.context_builder import BuiltContext, RAGContextBuilder
from backend.rag.prompt_templates import SYSTEM_PROMPT, build_rag_prompts
from backend.rag.rag_models import (
    CalculationEvidence,
    Citation,
    RAGAnswer,
    RAGCapabilitiesResponse,
    RAGRequest,
    RetrievedEvidence,
)
from backend.rag.rag_service import RAGService

__all__ = [
    "BuiltContext",
    "CalculationEvidence",
    "Citation",
    "CitationValidationResult",
    "CitationValidator",
    "RAGAnswer",
    "RAGCapabilitiesResponse",
    "RAGContextBuilder",
    "RAGRequest",
    "RAGService",
    "RetrievedEvidence",
    "SYSTEM_PROMPT",
    "build_rag_prompts",
]
