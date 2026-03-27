"""
LinkedIn Writer Agent — Phase 4, Content Variant Node.

Produces a polished standalone LinkedIn post for the concept, informed by the
completed guide HTML. Runs in parallel with reel_writer and diagram_generator
after the writer node completes.

Input state fields used:
    concept_name, category, guide_html, teaching_plan

Output state fields written:
    linkedin_post — str
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.state import PipelineState
from src.utils.llm import call_llm

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "linkedin_writer.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

# Truncate guide HTML — linkedin_writer only needs the prose sections, not full DOM
_MAX_GUIDE_CHARS = 12_000


async def linkedin_writer_node(state: PipelineState) -> dict:
    """
    LangGraph node: generate a standalone LinkedIn post from the completed guide.

    Returns only linkedin_post (ADR-010 — parallel node owns only its key).
    """
    from src.config import settings

    concept_name = state["concept_name"]
    logger.info("linkedin_writer: generating LinkedIn post for '%s'", concept_name)

    guide_html = state.get("guide_html", "")
    teaching_plan = state.get("teaching_plan", {})

    guide_excerpt = guide_html[:_MAX_GUIDE_CHARS]
    if len(guide_html) > _MAX_GUIDE_CHARS:
        guide_excerpt += "\n... [guide truncated]"

    user_message = f"""Concept: {concept_name}
Category: {state.get('category', '')}

Teaching hook (use as inspiration for your opening):
{teaching_plan.get('hook', '')}

Analogy (optional framing device):
{teaching_plan.get('analogy', '')}

Guide HTML (extract the key insight — do not copy verbatim):
{guide_excerpt}

Write the LinkedIn post now.""".strip()

    response = await call_llm(
        provider="anthropic",
        model=settings.default_writer_model,
        system_prompt=_SYSTEM_PROMPT,
        user_message=user_message,
        temperature=0.4,
        max_tokens=512,
    )

    raw = _strip_fences(response.content)
    try:
        parsed = json.loads(raw)
        linkedin_post = parsed.get("linkedin_post", "")
    except json.JSONDecodeError as exc:
        logger.error("linkedin_writer: JSON parse failed: %s", exc)
        linkedin_post = raw  # fall back to raw text if JSON wrapping fails

    logger.info("linkedin_writer: post generated (%d chars)", len(linkedin_post))

    # ADR-010: return only owned key
    return {"linkedin_post": linkedin_post}


def _strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        parts = s.split("```")
        if len(parts) >= 3:
            s = parts[1]
            if s.startswith("json"):
                s = s[4:]
    return s.strip()
