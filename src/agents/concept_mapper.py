"""
Concept Mapper Agent — Phase 2, Node 3.

Takes the repo-specific implementation evidence and generalizes it into a
portable software engineering pattern. Uses GPT-4o (strong at abstraction
and structured taxonomy) with Claude as fallback.

Input state fields used:
    concept_name, category, code_evidence, implementation_notes, doc_context

Output state fields written:
    generalized_pattern — portable SE pattern description
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.state import PipelineState
from src.utils.llm import call_llm

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "concept_mapper.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

_MAX_EVIDENCE_SNIPPETS = 6   # cap to keep prompt focused


async def concept_mapper_node(state: PipelineState) -> PipelineState:
    """
    LangGraph node: abstract the repo implementation into a general SE pattern.
    """
    from src.config import settings

    concept_name = state["concept_name"]
    code_evidence = state.get("code_evidence", [])
    implementation_notes = state.get("implementation_notes", {})
    doc_context = state.get("doc_context", {})

    logger.info("concept_mapper: generalizing pattern for '%s'", concept_name)

    # ── Build context for the LLM ─────────────────────────────────────────────
    evidence_text = _format_evidence(code_evidence[:_MAX_EVIDENCE_SNIPPETS])
    bug_stories_text = _format_bug_stories(doc_context.get("bug_stories", []))
    tradeoffs_text = "\n".join(
        f"- {t}" for t in doc_context.get("tradeoffs", [])
    ) or "(none documented)"

    user_message = f"""Concept: {concept_name}
Category: {state.get('category', '')}

Implementation summary (repo-specific):
{implementation_notes.get('implementation_summary', '(not available)')}

Feature rationale (from docs):
{doc_context.get('feature_rationale', '(not available)')}

Code evidence (selected snippets):
{evidence_text}

Bug stories from this codebase:
{bug_stories_text}

Trade-offs documented:
{tradeoffs_text}

Produce the generalized pattern JSON as specified.""".strip()

    # Prefer GPT-4o for abstraction/generalisation; fall back to Claude
    if settings.openai_configured:
        provider = "openai"
        model = settings.default_openai_model
    else:
        logger.info("concept_mapper: OpenAI not configured, falling back to Claude")
        provider = "anthropic"
        model = settings.default_research_model

    response = await call_llm(
        provider=provider,
        model=model,
        system_prompt=_SYSTEM_PROMPT,
        user_message=user_message,
        temperature=0.3,
        max_tokens=2048,
    )

    raw = _strip_fences(response.content)
    try:
        generalized_pattern = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("concept_mapper: JSON parse failed: %s", exc)
        generalized_pattern = {
            "pattern_name": concept_name,
            "general_description": implementation_notes.get("implementation_summary", ""),
            "naive_approach": "",
            "why_naive_fails": "",
            "production_approach": "",
            "applicable_domains": [],
            "anti_patterns": [],
            "use_when": [],
            "avoid_when": [],
            "analogy": "",
            "key_insight": "",
        }

    logger.info(
        "concept_mapper: mapped to pattern '%s' (%s)",
        generalized_pattern.get("pattern_name", "?"),
        provider,
    )

    return {**state, "generalized_pattern": generalized_pattern}


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


def _format_bug_stories(stories: list[dict]) -> str:
    if not stories:
        return "(none documented)"
    parts = []
    for s in stories:
        parts.append(
            f"Title: {s.get('title', '')}\n"
            f"Symptom: {s.get('symptom', '')}\n"
            f"Root cause: {s.get('root_cause', '')}\n"
            f"Fix: {s.get('fix', '')}\n"
            f"Lesson: {s.get('lesson', '')}"
        )
    return "\n\n".join(parts)


def _strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        parts = s.split("```")
        if len(parts) >= 3:
            s = parts[1]
            if s.startswith("json"):
                s = s[4:]
    return s.strip()
