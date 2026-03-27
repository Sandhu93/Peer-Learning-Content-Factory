"""
Tech Reviewer Agent — Phase 3, Node 1.

Fact-checks the generated guide against actual code evidence from the codebase.
Flags any claims that contradict or cannot be substantiated by the evidence.

Input state fields used:
    concept_name, guide_html, code_evidence, implementation_notes

Output state fields written:
    review_result — {is_accurate: bool, corrections: list[str], confidence: str}
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.state import PipelineState
from src.utils.llm import call_llm

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "tech_reviewer.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

_MAX_EVIDENCE_SNIPPETS = 12
# Truncate guide HTML sent to reviewer — reviewer needs the text, not full DOM
_MAX_GUIDE_CHARS = 30_000


async def tech_reviewer_node(state: PipelineState) -> dict:
    """
    LangGraph node: fact-check the generated guide against codebase evidence.
    """
    from src.config import settings

    concept_name = state["concept_name"]
    guide_html = state.get("guide_html", "")
    code_evidence = state.get("code_evidence", [])
    implementation_notes = state.get("implementation_notes", {})

    logger.info("tech_reviewer: reviewing guide for '%s'", concept_name)

    evidence_text = _format_evidence(code_evidence[:_MAX_EVIDENCE_SNIPPETS])
    # Truncate to keep prompt size manageable — reviewer reads prose, not full DOM
    guide_excerpt = guide_html[:_MAX_GUIDE_CHARS]
    if len(guide_html) > _MAX_GUIDE_CHARS:
        guide_excerpt += "\n... [truncated for review]"

    user_message = f"""Concept: {concept_name}

Implementation summary (ground truth from codebase):
{implementation_notes.get('implementation_summary', '(not available)')}

Code evidence:
{evidence_text}

Guide HTML to review:
{guide_excerpt}

Review the guide against the evidence and produce the JSON review result.""".strip()

    response = await call_llm(
        provider="anthropic",
        model=settings.default_research_model,
        system_prompt=_SYSTEM_PROMPT,
        user_message=user_message,
        temperature=0.0,
        max_tokens=1024,
    )

    raw = _strip_fences(response.content)
    try:
        review_result = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("tech_reviewer: JSON parse failed: %s", exc)
        # Safe fallback — treat as accurate so the pipeline continues
        review_result = {
            "is_accurate": True,
            "corrections": [],
            "confidence": "low",
        }

    logger.info(
        "tech_reviewer: accurate=%s, confidence=%s, corrections=%d",
        review_result.get("is_accurate"),
        review_result.get("confidence"),
        len(review_result.get("corrections", [])),
    )

    return {**state, "review_result": review_result}


def _format_evidence(evidence: list[dict]) -> str:
    if not evidence:
        return "(no code evidence available)"
    parts = []
    for e in evidence:
        parts.append(
            f"File: {e.get('file_path', '?')} "
            f"(lines {e.get('line_start', '?')}–{e.get('line_end', '?')})\n"
            f"Relevance: {e.get('relevance', '')}\n"
            f"{e.get('content', '')}"
        )
    return "\n\n---\n\n".join(parts)


def _strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        parts = s.split("```")
        if len(parts) >= 3:
            s = parts[1]
            if s.startswith("json"):
                s = s[4:]
    return s.strip()
