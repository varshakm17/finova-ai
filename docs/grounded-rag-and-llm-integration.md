# Finova AI — LLM Integration & Evidence-Grounded Financial RAG

**Session 08 Documentation**  
**Version:** 0.1.0  
**Status:** Implemented & Verified  

---

## 1. Overview & Objectives

In Session 08, Finova AI bridges its multi-stage information retrieval infrastructure with a locally executable Large Language Model (LLM) to deliver **Evidence-Grounded Financial Retrieval-Augmented Generation (RAG)**.

Corporate financial research demands extreme factual precision, complete citation auditability, and absolute intolerance for numerical hallucinations. Finova AI implements a production-grade RAG pipeline that synthesizes answers strictly from verified SEC filing disclosures (10-K, 10-Q) and deterministic Python financial calculation receipts.

### Key Capabilities Introduced in Session 08
1. **Vendor-Agnostic LLM Provider Abstraction**: Pluggable interface (`LLMProvider`) supporting local free Ollama (`OllamaProvider`) with CPU-friendly instruction models (default: `qwen2.5:3b`), timeout resilience, health auditing, and a deterministic offline test provider (`MockLLMProvider`).
2. **Multi-Modal Evidence Context Builder**: Orchestrates candidate retrieval via Hybrid Search (FAISS dense + BM25 sparse + RRF), Cross-Encoder reranking, statutory provenance verification, and dynamic injection of deterministic XBRL calculation receipts from SQLite.
3. **Strict Citation Prompt Templates**: System and user prompt architecture enforcing evidence-only grounding, explicit bracketed citations (`[E1]`, `[C1]`), period awareness, refusal to hallucinate arithmetic, and regulatory anti-advice guardrails.
4. **Automated Citation Validator & Provenance Auditor**: Regular expression extraction of cited IDs (`[E1]`, `[C1]`), validation against prompt context, mapping to official SEC EDGAR archive links, detection of fabricated citations, and status classification (`answered`, `partially_supported`, `citation_validation_failed`, `insufficient_evidence`).
5. **RAG Orchestration Service & Answer Persistence**: Central service (`RAGService`) managing query lifecycles, insufficient evidence thresholds, offline provider fallbacks, and persistent storage of answers and audit trails in SQLite table `research_answers`.
6. **FastAPI Endpoints**: 4 high-performance REST routes for asking questions, retrieving stored answers, inspecting provider status, and querying RAG system capabilities.
7. **Streamlit "Financial Research Assistant"**: Interactive analytics workspace featuring provider health indicators, query filters, response depth selection, citation inspection badges, original SEC text excerpts, and calculation receipts.

---

## 2. LLM Provider Architecture

Finova AI implements a decoupled LLM abstraction layer in `backend/llm/` designed for CPU-only local execution with zero API subscription costs.

```
+-------------------------------------------------------------------+
|                        LLMProvider (ABC)                          |
|  - provider_name: str                                             |
|  - model_name: str                                                |
|  - generate(prompt, system_prompt, max_tokens, temperature)       |
|  - health_check() -> bool                                         |
|  - get_model_info() -> dict                                       |
+---------------------------------+---------------------------------+
                                  |
            +---------------------+---------------------+
            |                                           |
+-----------v-----------+                   +-----------v-----------+
|    OllamaProvider     |                   |    MockLLMProvider    |
| - Local HTTP daemon   |                   | - 100% offline        |
| - CPU-quantized models|                   | - Deterministic mocks |
| - Health via /api/tags|                   | - Zero network calls  |
| - Auto timeout/retry  |                   | - Automated testing   |
+-----------------------+                   +-----------------------+
```

### Supported Provider Implementations
- **`OllamaProvider` (`backend/llm/ollama_provider.py`)**: Connects to a local Ollama daemon (`http://127.0.0.1:11434`) via HTTPX. Employs lightweight quantized instruction models such as `qwen2.5:3b` or `llama3.2:3b`. Includes comprehensive health checks (`/api/version`, `/api/tags`), non-blocking timeouts, error mapping, and token usage accounting.
- **`MockLLMProvider` (`backend/llm/llm_provider.py`)**: Deterministic mock provider for unit and regression testing. Simulates successful generation, multi-citation responses, and offline scenarios without requiring any network connections or downloaded weights.
- **Provider Factory (`backend/llm/__init__.py`)**: `get_llm_provider(provider_type, settings)` resolves the active provider based on configuration (`LLM_PROVIDER=ollama` or `LLM_PROVIDER=mock`).

---

## 3. Context Builder & Multi-Modal Evidence Assembly

The context builder (`backend/rag/context_builder.py`) transforms unstructured filing text and structured XBRL calculations into a unified, citation-ready prompt context:

```
User Financial Question
       |
       +---> [1] Identify Referenced Financial Metrics (Regex keyword map)
       |           |
       |           +---> Query SQLite `financial_calculations` ---> [C1], [C2] Receipts
       |
       +---> [2] Candidate Retrieval via HybridSearchService (FAISS + BM25 + RRF)
       |           |
       |           +---> [3] Cross-Encoder Reranking (`ms-marco-MiniLM-L-6-v2`)
       |           |
       |           +---> [4] Evidence Quality Validation (Provenance & Whitelist)
       |           |
       |           +---> Formatted Statutory Filing Passages ---> [E1], [E2] Passages
       |
       v
Assembled Citation Context String (Budget-Checked <= 12,000 chars)
```

### Context Budgeting & Truncation
When assembled context exceeds `RAG_MAX_CONTEXT_CHARACTERS` (default: 12,000 characters), `RAGContextBuilder` systematically prunes lowest-ranked filing passages while preserving deterministic calculation receipts and emitting audit warnings.

---

## 4. Prompt Engineering & Regulatory Guardrails

Prompt templates in `backend/rag/prompt_templates.py` enforce strict operational constraints:

### System Prompt Guardrails
1. **Strict Grounding**: Synthesizes answers strictly and exclusively from supplied evidence. Forbids speculation or extrapolation.
2. **Citation Traceability**: Every claim must carry inline citations using brackets (`[E1]`, `[E2]`, `[C1]`).
3. **Zero Arithmetic Hallucination**: Models are forbidden from calculating financial ratios, margins, or growth rates. All quantitative calculations must originate from `[C1]`, `[C2]` calculation receipts generated deterministically by Python.
4. **Temporal Awareness**: Explicitly distinguishes fiscal reporting periods (e.g. FY2022 vs FY2023). Prohibits treating different periods as interchangeable.
5. **Honest Uncertainty**: Mandates returning explicit refusal text ("The available SEC filing disclosures do not provide sufficient evidence to answer this question.") when evidence is lacking.
6. **No Investment Advice**: Enforces objective financial synthesis; prohibits price targets, buy/sell ratings, or investment advice.

---

## 5. Citation Validation & Provenance Auditing

`CitationValidator` (`backend/rag/citation_validator.py`) inspects LLM completions before delivering them to users:

```python
# Extraction Regex: Bracketed tags [E1], [C1], [E1, E2], [E1, C1]
CITATION_TAG_PATTERN = re.compile(r"\[([EC]\d+(?:\s*,\s*[EC]\d+)*)\]", re.IGNORECASE)
```

### Audit Status Matrix
| Validation Condition | Resulting `answer_status` | Description |
| :--- | :--- | :--- |
| All cited `[E#]`/`[C#]` exist in context | `answered` | Complete evidence support. Citations mapped to source SEC URLs and text snippets. |
| Citations present, but some IDs absent from context | `partially_supported` | Answer contains valid citations alongside unsupported/fabricated IDs. Audit warning emitted. |
| Zero valid citations, but hallucinated IDs present | `citation_validation_failed` | Generated text fabricated references without using supplied context. |
| Factual claims made without any citations | `partially_supported` | Uncited assertions flagged with audit warning. |
| Context insufficient or answer declares lack of evidence | `insufficient_evidence` | Refusal to speculate; honest uncertainty declaration. |

---

## 6. RAG Orchestration Service & Database Schema

The RAG pipeline is orchestrated by `RAGService` (`backend/rag/rag_service.py`), which coordinates retrieval, validation, generation, and persistence.

### SQLite Schema: `research_answers`
```sql
CREATE TABLE IF NOT EXISTS research_answers (
    answer_id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    ticker TEXT,
    answer_text TEXT NOT NULL,
    answer_status TEXT NOT NULL,
    provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    retrieval_method TEXT NOT NULL,
    citations_json TEXT NOT NULL,
    retrieved_evidence_json TEXT NOT NULL,
    calculation_evidence_json TEXT NOT NULL,
    generation_metadata_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_answers_ticker ON research_answers (ticker);
CREATE INDEX IF NOT EXISTS idx_answers_created_at ON research_answers (created_at);
```

---

## 7. REST API Endpoints

### 1. `POST /api/v1/research/ask`
Submits a financial research question and returns an evidence-grounded answer with verified citations.

- **Request Body (`RAGRequest`)**:
  ```json
  {
    "question": "What were Apple's primary risk factors and operating margin in 2023?",
    "ticker": "AAPL",
    "filing_type": "10-K",
    "section_identifier": "ITEM_1A",
    "top_k": 5,
    "use_reranker": true,
    "include_calculations": true,
    "response_style": "detailed"
  }
  ```
- **Response (`RAGAnswer`)**:
  ```json
  {
    "answer_id": "ans_a1b2c3d4e5f6",
    "question": "What were Apple's primary risk factors and operating margin in 2023?",
    "answer": "Apple identified global supply chain concentration as a key risk [E1]. Its operating margin was 30.13% [C1].",
    "answer_status": "answered",
    "citations": [
      {
        "citation_id": "E1",
        "evidence_type": "filing_passage",
        "source_reference": "AAPL 10-K (2023-11-03) ITEM_1A",
        "source_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
        "excerpt": "Global economic volatility and supply chain concentration represent principal risks."
      },
      {
        "citation_id": "C1",
        "evidence_type": "calculation_receipt",
        "source_reference": "Deterministic Calc: operating_margin (2023-09-30) = 30.13 percentage",
        "source_url": "https://www.sec.gov/edgar",
        "excerpt": "Formula: OperatingIncome / TotalRevenue"
      }
    ],
    "model_name": "qwen2.5:3b",
    "provider": "ollama",
    "retrieval_method": "hybrid_reranked",
    "generation_metadata": {
      "latency_ms": 1420.5,
      "tokens_generated": 68,
      "prompt_tokens": 482
    },
    "warnings": []
  }
  ```

### 2. `GET /api/v1/research/answers/{answer_id}`
Retrieves a previously computed answer and its complete provenance trail from SQLite. Returns `404 Not Found` if the identifier does not exist.

### 3. `GET /api/v1/llm/status`
Returns provider health, active model, reachability, timeout settings, and context parameters:
```json
{
  "provider": "ollama",
  "model": "qwen2.5:3b",
  "online": true,
  "base_url": "http://127.0.0.1:11434",
  "timeout": 45.0,
  "temperature": 0.1,
  "max_tokens": 1024,
  "context_window": 4096
}
```

### 4. `GET /api/v1/research/capabilities`
Returns operational capabilities of the RAG pipeline including retrieval modes, reranker readiness, deterministic calculation engine integration, and citation verification status.

---

## 8. Streamlit Frontend Integration

The Streamlit UI (`frontend/app.py`) includes a dedicated **Financial Research Assistant** workspace:
- **Live Provider Status Pill**: Displays provider name, model, and online/offline status with troubleshooting instructions.
- **Interactive Query Formulation**: Text area for question input, company ticker filter, filing type selector, section selector, and response style toggle (`detailed`, `concise`, `bullet_points`).
- **Advanced Retrieval Toggles**: Sliders and checkboxes for Top-K candidate count, Cross-Encoder reranker, and deterministic calculation receipts.
- **Evidence-Grounded Answer Display**: Card layout with status badge (`Answered & Verified`, `Partially Supported`, `Insufficient Evidence`), model name, and generation latency.
- **Interactive Provenance Inspection**: Expandable tabs for verified statutory citations with live SEC EDGAR links, retrieved raw filing chunks with hybrid/reranker scores, and deterministic calculation formulas.

---

## 9. Verification & Test Suite

The test suite enforces **100% offline testing** with zero network calls and zero model downloads during `pytest` execution:
- `tests/test_llm_provider.py`: Mock provider behavior, custom responses, offline simulation, Ollama error handling, timeout mappings, model availability checks, and provider factory resolution.
- `tests/test_prompt_templates.py`: Operational rules, system prompt guardrails, and style prompt assembly.
- `tests/test_citation_validator.py`: Bracket citation extraction, multi-citation tags, valid citation mapping to EDGAR links, unsupported citation detection, and insufficient evidence handling.
- `tests/test_context_builder.py`: Multi-modal evidence assembly, metric keyword identification, calculation receipt querying, accession filtering, and temporal mismatch warnings.
- `tests/test_rag_service.py`: End-to-end question answering with `MockLLMProvider`, insufficient evidence threshold validation, provider offline handling, generation exception recovery, and SQLite persistence.
- `tests/test_api_rag.py`: TestClient integration testing for all 4 new FastAPI routes.

### Test Execution Summary
```
collected 257 items
257 passed in 35.05s
Overall Repository Coverage: 89%
Session 08 (backend.llm & backend.rag) Coverage: 92%
Ruff Linting & Formatting: 100% clean (0 errors)
```

---

## 10. Scope Boundaries

To maintain software engineering rigor and modularity:
- **No LangGraph or multi-agent orchestration** in Session 08 (reserved for subsequent multi-agent coordination sessions).
- **No supervisor agent or autonomous tool-calling loops**.
- **No model fine-tuning or parameter updates**.
- **Zero reliance on commercial, paid, or closed-source LLM APIs** (OpenAI, Anthropic, Google Gemini paid tiers).
- **Zero LLM arithmetic**: all numerical margins, ratios, and growth rates are computed exclusively by Python.
