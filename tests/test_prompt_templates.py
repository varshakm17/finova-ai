"""Unit tests for RAG prompt templates and formatting."""

from backend.rag.prompt_templates import SYSTEM_PROMPT, build_rag_prompts


def test_system_prompt_operational_rules() -> None:
    assert "Finova AI" in SYSTEM_PROMPT
    assert "STRICT GROUNDING" in SYSTEM_PROMPT
    assert "CITATION TRACEABILITY" in SYSTEM_PROMPT
    assert "PREVENT ARITHMETIC HALLUCINATIONS" in SYSTEM_PROMPT
    assert "TEMPORAL DISTINCTIONS" in SYSTEM_PROMPT
    assert "HONEST UNCERTAINTY" in SYSTEM_PROMPT
    assert "NO INVESTMENT ADVICE" in SYSTEM_PROMPT


def test_build_rag_prompts_styles() -> None:
    context_text = "[E1] Apple 10-K: Revenues grew 5% in FY2023."
    question = "How much did revenues grow?"

    # Detailed style
    sys_p, user_p = build_rag_prompts(question, context_text, response_style="detailed")
    assert sys_p == SYSTEM_PROMPT
    assert context_text in user_p
    assert question in user_p
    assert "comprehensive" in user_p

    # Concise style
    _, user_p_concise = build_rag_prompts(
        question, context_text, response_style="concise"
    )
    assert "1-2 paragraph" in user_p_concise

    # Bullet points style
    _, user_p_bullets = build_rag_prompts(
        question, context_text, response_style="bullet_points"
    )
    assert "bullet-point breakdown" in user_p_bullets
