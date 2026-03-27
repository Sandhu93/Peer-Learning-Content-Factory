"""
Code Researcher Agent — Phase 1, Node 2.

Searches the target codebase for evidence of the concept and builds a
structured evidence pack.

Input state fields used:
    concept_name, teaching_plan.repo_search_strategy, repo_anchors

Output state fields written:
    code_evidence — list of CodeSnippet dicts
"""

from __future__ import annotations

import json
import logging
from pathlib import Path


from src.state import PipelineState
from src.tools.code_search import (
    find_tests,
    read_file_range,
    search_pattern,
    search_term,
)
from src.utils.llm import call_llm

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "code_researcher.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

_MAX_SEARCH_RESULTS = 15  # per search term


async def code_researcher_node(state: PipelineState) -> PipelineState:
    """
    LangGraph node: gather code evidence from the target repo.
    """
    from src.config import settings

    concept_name = state["concept_name"]
    teaching_plan = state.get("teaching_plan", {})
    search_strategy = teaching_plan.get("repo_search_strategy", {})
    repo_anchors = state.get("repo_anchors", [])

    # repo_path travels in state; fall back to settings for backwards compat
    repo_path = Path(state["repo_path"]) if state.get("repo_path") else settings.repo_path

    primary_terms = search_strategy.get("primary_terms", repo_anchors)
    secondary_terms = search_strategy.get("secondary_terms", [])

    logger.info("code_researcher: searching for '%s' in %s", concept_name, repo_path)

    # ── Step 1: Gather raw search results ────────────────────────────────────
    raw_results: list[dict] = []

    for term in primary_terms[:5]:  # cap to avoid token explosion
        hits = search_term(term, repo_path)
        raw_results.extend(hits[:5])

    for term in secondary_terms[:3]:
        hits = search_term(term, repo_path)
        raw_results.extend(hits[:3])

    test_hits = find_tests(concept_name, repo_path)
    raw_results.extend(test_hits[:5])

    # Deduplicate by (file, line_number)
    seen: set[tuple[str, int]] = set()
    unique_results: list[dict] = []
    for r in raw_results:
        key = (r["file"], r["line_number"])
        if key not in seen:
            seen.add(key)
            unique_results.append(r)

    logger.info("code_researcher: found %d unique hits", len(unique_results))

    # ── Step 2: Ask Claude to synthesize into structured evidence ─────────────
    hits_text = _format_hits(unique_results)

    user_message = f"""
Concept: {concept_name}
Category: {state.get('category', '')}
Why it matters: {state.get('why_it_matters', '')}

Search terms used: {', '.join(primary_terms + secondary_terms)}

Raw search results from the codebase:
{hits_text}

Produce the structured code evidence JSON as specified.
""".strip()

    response = await call_llm(
        provider="anthropic",
        model=settings.default_research_model,
        system_prompt=_SYSTEM_PROMPT,
        user_message=user_message,
        temperature=0.0,
        max_tokens=4096,
    )

    raw = _strip_fences(response.content)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("code_researcher: JSON parse failed: %s", exc)
        parsed = {"code_evidence": [], "implementation_summary": "", "gaps": []}

    # Store implementation_summary in doc_context (will be merged by doc_analyzer)
    doc_context = state.get("doc_context", {})
    doc_context["implementation_summary"] = parsed.get("implementation_summary", "")
    doc_context["evidence_gaps"] = parsed.get("gaps", [])

    return {
        **state,
        "code_evidence": parsed.get("code_evidence", []),
        "doc_context": doc_context,
    }


def _format_hits(hits: list[dict]) -> str:
    if not hits:
        return "(no matches found)"
    lines = []
    for h in hits[:_MAX_SEARCH_RESULTS]:
        lines.append(f"  File: {h['file']} (line {h['line_number']})")
        lines.append(f"  Match: {h['line_text']}")
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
