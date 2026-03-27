"""
Reel Writer Agent — Phase 4, Content Variant Node.

Produces a polished 60-second video reel script for the concept, informed by
the completed guide HTML. Uses GPT-4o with a Claude Sonnet fallback.
Runs in parallel with linkedin_writer and diagram_generator after writer completes.

Input state fields used:
    concept_name, category, guide_html, teaching_plan

Output state fields written:
    reel_script — str  (formatted plain text for reel_script.md)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.state import PipelineState
from src.utils.llm import call_llm

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "reel_writer.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

# Reel writer only needs the core narrative from the guide
_MAX_GUIDE_CHARS = 10_000


async def reel_writer_node(state: PipelineState) -> dict:
    """
    LangGraph node: generate a standalone 60-second reel script from the guide.

    Tries GPT-4o first; falls back to Claude Sonnet on failure.
    Returns only reel_script (ADR-010 — parallel node owns only its key).
    """
    from src.config import settings

    concept_name = state["concept_name"]
    logger.info("reel_writer: generating reel script for '%s'", concept_name)

    guide_html = state.get("guide_html", "")
    teaching_plan = state.get("teaching_plan", {})

    guide_excerpt = guide_html[:_MAX_GUIDE_CHARS]
    if len(guide_html) > _MAX_GUIDE_CHARS:
        guide_excerpt += "\n... [guide truncated]"

    user_message = f"""Concept: {concept_name}
Category: {state.get('category', '')}

Hook (use as inspiration for the opening scene):
{teaching_plan.get('hook', '')}

Analogy (optional framing device):
{teaching_plan.get('analogy', '')}

Guide HTML (extract the core story — do not reproduce verbatim):
{guide_excerpt}

Write the 6-scene reel script now.""".strip()

    scenes = await _call_with_fallback(settings, user_message)

    reel_script = _format_reel_script(scenes)
    logger.info("reel_writer: script generated (%d chars, %d scenes)", len(reel_script), len(scenes))

    # ADR-010: return only owned key
    return {"reel_script": reel_script}


async def _call_with_fallback(settings, user_message: str) -> list[dict]:
    """Try GPT-4o first; fall back to Claude Sonnet."""
    if settings.openai_configured:
        try:
            response = await call_llm(
                provider="openai",
                model=settings.default_openai_model,
                system_prompt=_SYSTEM_PROMPT,
                user_message=user_message,
                temperature=0.4,
                max_tokens=1024,
            )
            scenes = _parse_scenes(response.content)
            if scenes:
                logger.info("reel_writer: used GPT-4o")
                return scenes
            logger.warning("reel_writer: GPT-4o returned no scenes — falling back to Claude")
        except Exception as exc:
            logger.warning("reel_writer: GPT-4o failed (%s) — falling back to Claude", exc)

    # Claude fallback
    response = await call_llm(
        provider="anthropic",
        model=settings.default_writer_model,
        system_prompt=_SYSTEM_PROMPT,
        user_message=user_message,
        temperature=0.4,
        max_tokens=1024,
    )
    logger.info("reel_writer: used Claude Sonnet (fallback)")
    return _parse_scenes(response.content)


def _parse_scenes(raw: str) -> list[dict]:
    raw = _strip_fences(raw)
    try:
        parsed = json.loads(raw)
        return parsed.get("reel_scenes", [])
    except json.JSONDecodeError as exc:
        logger.error("reel_writer: JSON parse failed: %s", exc)
        return []


def _format_reel_script(scenes: list[dict]) -> str:
    """Convert scene dicts to a readable plain-text reel_script.md format."""
    if not scenes:
        return ""
    lines = []
    for scene in scenes:
        lines.append(f"[{scene.get('timestamp', '')}] {scene.get('title', '')}")
        lines.append(f"Visual: {scene.get('visual', '')}")
        lines.append(scene.get("script", ""))
        lines.append("")
    return "\n".join(lines)


def _strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        parts = s.split("```")
        if len(parts) >= 3:
            s = parts[1]
            if s.startswith("json"):
                s = s[4:]
    return s.strip()
