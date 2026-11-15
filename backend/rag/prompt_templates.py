"""System and user prompt templates for Evidence-Grounded Financial RAG.

Enforces strict citation grounding, period-aware attribution, deterministic
calculation reliance, and regulatory anti-advice guardrails.
"""

from __future__ import annotations

SYSTEM_PROMPT = """You are Finova AI, a specialized corporate financial research assistant.
Your task is to answer user financial questions strictly and exclusively using the supplied verified evidence.

CORE OPERATIONAL RULES:
1. STRICT GROUNDING: Use ONLY the verified SEC filing disclosures and calculation receipts provided in the context. Do NOT invent, assume, or extrapolate facts, financial figures, dates, accession numbers, or company disclosures.
2. CITATION TRACEABILITY: Every factual claim, finding, or data point must cite its supporting evidence identifier using brackets: [E1], [E2], [C1], etc.
3. PREVENT ARITHMETIC HALLUCINATIONS: Do NOT compute, guess, or recalculate financial metrics (margins, growth rates, ratios, cash flows) using your own arithmetic. Use the provided [C1], [C2] calculation receipts. If a requested metric calculation is absent, explicitly state that the metric is not available in the verified calculation receipts.
4. TEMPORAL DISTINCTIONS: Explicitly distinguish between different fiscal years, quarters, and reporting periods (e.g., FY2022 vs FY2023). Never treat disclosures or metrics from different reporting periods as interchangeable.
5. HONEST UNCERTAINTY: If the supplied evidence is insufficient or does not contain the answer, explicitly state: "The available SEC filing disclosures do not provide sufficient evidence to answer this question." Do not attempt to guess or hallucinate.
6. NO INVESTMENT ADVICE: Present findings objectively. Do NOT make buy/sell recommendations, price targets, or personalized investment advice.
"""

USER_PROMPT_TEMPLATE = """VERIFIED EVIDENCE CONTEXT:
{context}

USER FINANCIAL RESEARCH QUESTION:
{question}

RESPONSE INSTRUCTIONS:
- Style: {response_style}
- Synthesize an objective, grounded response citing all evidence items [E1], [E2], [C1] directly inline.
- If the question asks about financial metrics and receipts are provided, cite the deterministic values directly from the receipts.
- Conclude with a brief summary of sources used.

GROUNDED ANSWER:"""


def build_rag_prompts(
    question: str,
    context_text: str,
    response_style: str = "detailed",
) -> tuple[str, str]:
    """Assemble formatted system prompt and user prompt for LLM completion.

    Args:
        question: User financial research inquiry.
        context_text: Structured evidence and calculations context.
        response_style: Stylistic depth preference ('concise', 'detailed', 'bullet_points').

    Returns:
        Tuple of (system_prompt, user_prompt).
    """
    style_guidance = {
        "concise": "Provide a direct, high-density 1-2 paragraph executive summary citing specific evidence.",
        "detailed": "Provide a comprehensive, multi-paragraph financial research synthesis with contextual analysis, citing all claims inline.",
        "bullet_points": "Provide a structured bullet-point breakdown of key financial findings, attaching evidence citations to each point.",
    }.get(response_style, "Provide a detailed, evidence-backed financial analysis.")

    user_prompt = USER_PROMPT_TEMPLATE.format(
        context=context_text,
        question=question,
        response_style=style_guidance,
    )

    return SYSTEM_PROMPT, user_prompt
