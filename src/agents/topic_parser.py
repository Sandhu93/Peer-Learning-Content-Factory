"""
Topic Parser Agent — Phase 1, Node 1.

Enriches a raw ConceptRecord from the markdown backlog into a fully structured
fact sheet that subsequent agents can build on.

Input state fields used:
    concept_name, category, why_it_matters, repo_anchors

Output state fields written:
    concept_name (canonicalized), category, why_it_matters,
    teaching_plan (partial: difficulty, prerequisites, related_concepts,
                   common_misconceptions, key_terms, teaching_angles,
                   repo_search_strategy)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.state import PipelineState
from src.utils.llm import call_llm

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "topic_parser.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


async def topic_parser_node(state: PipelineState) -> PipelineState:
    """
    LangGraph node: enriches the concept entry into a structured fact sheet.
    """
    from src.config import settings

    concept_name = state["concept_name"]
    category = state.get("category", "")
    why_it_matters = state.get("why_it_matters", "")
    repo_anchors = state.get("repo_anchors", [])

    logger.info("topic_parser: processing '%s'", concept_name)

    user_message = f"""
Concept: {concept_name}
Category: {category}
Why it matters: {why_it_matters}
Repo anchors (search terms found in the codebase): {', '.join(repo_anchors)}

Produce the enriched fact sheet JSON as specified.
""".strip()

    response = await call_llm(
        provider="anthropic",
        model=settings.default_research_model,
        system_prompt=_SYSTEM_PROMPT,
        user_message=user_message,
        temperature=0.0,
    )

    raw = response.content.strip()
    # Strip markdown code fences if the model wrapped the output anyway
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("topic_parser: JSON parse failed: %s\nRaw:\n%s", exc, raw[:500])
        parsed = {}

    # Merge into state — teaching_plan holds structured metadata
    teaching_plan = state.get("teaching_plan", {})
    teaching_plan.update({
        "difficulty": parsed.get("difficulty", "intermediate"),
        "prerequisites": parsed.get("prerequisites", []),
        "related_concepts": parsed.get("related_concepts", []),
        "common_misconceptions": parsed.get("common_misconceptions", []),
        "key_terms": parsed.get("key_terms", {}),
        "teaching_angles": parsed.get("teaching_angles", []),
        "repo_search_strategy": parsed.get("repo_search_strategy", {
            "primary_terms": repo_anchors,
            "secondary_terms": [],
            "file_patterns": ["*.py"],
            "test_patterns": [],
        }),
    })

    return {
        **state,
        "concept_name": parsed.get("concept_name", concept_name),
        "category": parsed.get("category", category),
        "why_it_matters": parsed.get("why_it_matters", why_it_matters),
        "teaching_plan": teaching_plan,
    }
