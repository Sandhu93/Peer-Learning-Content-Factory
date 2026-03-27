"""
Pedagogy Planner Agent — Phase 2, Node 4.

Reads the full research package (code evidence, doc context, generalized
pattern) and produces the teaching plan: difficulty, sections, diagram
specifications, discussion prompts, and framing decisions for the writer.

Input state fields used:
    concept_name, category, why_it_matters, teaching_plan (from topic_parser),
    code_evidence, implementation_notes, doc_context, generalized_pattern

Output state fields written:
    teaching_plan   — enriched with pedagogy decisions (merged with Phase 1 plan)
    diagram_specs   — list of DiagramSpec dicts ready for the SVG renderer
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.state import PipelineState
from src.utils.llm import call_llm

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "pedagogy_planner.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


async def pedagogy_planner_node(state: PipelineState) -> PipelineState:
    """
    LangGraph node: plan the teaching structure for the guide.
    """
    from src.config import settings

    concept_name = state["concept_name"]
    generalized_pattern = state.get("generalized_pattern", {})
    code_evidence = state.get("code_evidence", [])
    doc_context = state.get("doc_context", {})
    implementation_notes = state.get("implementation_notes", {})

    logger.info("pedagogy_planner: planning guide structure for '%s'", concept_name)

    user_message = f"""Concept: {concept_name}
Category: {state.get('category', '')}
Why it matters: {state.get('why_it_matters', '')}

Generalized pattern:
{json.dumps(generalized_pattern, indent=2)}

Implementation summary (repo-specific):
{implementation_notes.get('implementation_summary', '(not available)')}

Code evidence ({len(code_evidence)} snippets found):
{_summarize_evidence(code_evidence)}

Doc context:
- Feature rationale: {doc_context.get('feature_rationale', '(not available)')}
- Bug stories found: {len(doc_context.get('bug_stories', []))}
- Trade-offs documented: {len(doc_context.get('tradeoffs', []))}
- Doc quality: {doc_context.get('doc_quality', 'unknown')}

Produce the pedagogy plan JSON as specified.""".strip()

    response = await call_llm(
        provider="anthropic",
        model=settings.default_research_model,
        system_prompt=_SYSTEM_PROMPT,
        user_message=user_message,
        temperature=0.2,
        max_tokens=3000,
    )

    raw = _strip_fences(response.content)
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("pedagogy_planner: JSON parse failed: %s", exc)
        plan = _fallback_plan(state)

    # Merge with Phase 1 teaching_plan (keep Phase 1 keys, extend with Phase 2 keys)
    existing_plan = state.get("teaching_plan", {})
    merged_plan = {**existing_plan, **plan}

    diagram_specs = plan.get("diagram_specs", [])
    logger.info(
        "pedagogy_planner: plan ready — difficulty=%s, %d diagrams",
        plan.get("difficulty", "?"),
        len(diagram_specs),
    )

    return {
        **state,
        "teaching_plan": merged_plan,
        "diagram_specs": diagram_specs,
    }


def _summarize_evidence(evidence: list[dict]) -> str:
    if not evidence:
        return "(none)"
    lines = []
    for e in evidence[:8]:
        lines.append(f"  - {e.get('file_path', '?')} L{e.get('line_start', '?')}: {e.get('relevance', '')}")
    return "\n".join(lines)


def _fallback_plan(state: PipelineState) -> dict:
    return {
        "difficulty": "intermediate",
        "hook": f"Here's what happens when {state.get('concept_name', 'this pattern')} is missing from production.",
        "analogy": "",
        "sections_to_include": [
            "problem_framing", "naive_vs_production", "how_it_works",
            "code_walkthrough", "bug_story", "tradeoffs", "discussion_prompts",
        ],
        "comparison_framing": "Without Pattern vs With Pattern",
        "code_example_strategy": "Show the primary implementation class and its main method.",
        "diagram_specs": [],
        "bug_story_source": "synthesized",
        "discussion_prompts": [
            "What failure scenario does this pattern prevent?",
            "What are the configuration trade-offs?",
            "When would you NOT use this pattern?",
            "How would you test this in isolation?",
        ],
        "key_terms": [],
    }


def _strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        parts = s.split("```")
        if len(parts) >= 3:
            s = parts[1]
            if s.startswith("json"):
                s = s[4:]
    return s.strip()
