"""
Editor Agent — Phase 3, Node 2.

Polishes the guide and applies factual corrections from tech_reviewer.
Does NOT add new technical content — accuracy corrections and prose polish only.

Strategy: asks Claude for a list of (original_text → replacement_text) pairs,
then applies them as string replacements to the HTML. This avoids re-generating
the full 40k+ char template and keeps the HTML structure intact.

Input state fields used:
    concept_name, guide_html, review_result

Output state fields written:
    guide_html — updated with corrections and polish
    editor_result — {changes_made: list[str]}
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.state import PipelineState
from src.utils.llm import call_llm

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "editor.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

# Send enough HTML for the editor to find passages; truncate the rest
_MAX_GUIDE_CHARS = 25_000


async def editor_node(state: PipelineState) -> dict:
    """
    LangGraph node: polish the guide and apply corrections from tech_reviewer.
    """
    from src.config import settings

    concept_name = state["concept_name"]
    guide_html = state.get("guide_html", "")
    review_result = state.get("review_result", {})

    logger.info("editor: polishing guide for '%s'", concept_name)

    corrections = review_result.get("corrections", [])
    corrections_text = (
        "\n".join(f"- {c}" for c in corrections)
        if corrections
        else "(none — guide was marked accurate)"
    )

    guide_excerpt = guide_html[:_MAX_GUIDE_CHARS]
    if len(guide_html) > _MAX_GUIDE_CHARS:
        guide_excerpt += "\n... [truncated]"

    user_message = f"""Concept: {concept_name}

Corrections to apply (from tech_reviewer):
{corrections_text}

Guide HTML:
{guide_excerpt}

Produce the JSON edit list as specified.""".strip()

    response = await call_llm(
        provider="anthropic",
        model=settings.default_writer_model,
        system_prompt=_SYSTEM_PROMPT,
        user_message=user_message,
        temperature=0.2,
        max_tokens=2048,
    )

    raw = _strip_fences(response.content)
    try:
        edit_result = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("editor: JSON parse failed: %s", exc)
        edit_result = {"changes": [], "changes_made": ["Editor parse failed — guide unchanged."]}

    # Apply string replacements to the guide HTML
    updated_html = guide_html
    applied = 0
    for change in edit_result.get("changes", []):
        original = change.get("original", "")
        replacement = change.get("replacement", "")
        if original and original in updated_html:
            updated_html = updated_html.replace(original, replacement, 1)
            applied += 1
        elif original:
            logger.warning("editor: passage not found in HTML — skipping change")

    changes_made = edit_result.get("changes_made", [])
    logger.info(
        "editor: applied %d/%d changes for '%s'",
        applied,
        len(edit_result.get("changes", [])),
        concept_name,
    )

    editor_result = {"changes_made": changes_made}
    return {**state, "guide_html": updated_html, "editor_result": editor_result}


def _strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        parts = s.split("```")
        if len(parts) >= 3:
            s = parts[1]
            if s.startswith("json"):
                s = s[4:]
    return s.strip()
