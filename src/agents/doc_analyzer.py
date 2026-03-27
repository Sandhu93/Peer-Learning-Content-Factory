"""
Doc Analyzer Agent — Phase 2, Node 2 (parallel with code_researcher).

Reads documentation files from the target repository and extracts narrative
context: the rationale behind design decisions, bug stories that drove
architecture choices, explicit trade-offs, and evolution notes.

Runs in parallel with code_researcher. Writes exclusively to `doc_context`
to avoid state-merge conflicts with code_researcher's `code_evidence` and
`implementation_notes` writes.

Input state fields used:
    concept_name, category, repo_path

Output state fields written:
    doc_context — {feature_rationale, bug_stories[], tradeoffs[], evolution_notes, doc_quality}
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.state import PipelineState
from src.tools.file_reader import find_doc_files, read_doc_file
from src.utils.llm import call_llm

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "doc_analyzer.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

_MAX_DOC_CHARS = 6000   # per file — keep total prompt manageable


async def doc_analyzer_node(state: PipelineState) -> PipelineState:
    """
    LangGraph node: read repo docs and extract narrative context.
    """
    from src.config import settings

    concept_name = state["concept_name"]
    repo_path = Path(state["repo_path"]) if state.get("repo_path") else settings.repo_path

    logger.info("doc_analyzer: reading documentation from %s", repo_path)

    # ── Step 1: Discover and read documentation files ─────────────────────────
    doc_files = find_doc_files(repo_path)
    doc_sections: list[str] = []

    for doc_path in doc_files:
        content = read_doc_file(doc_path, max_chars=_MAX_DOC_CHARS)
        if content.strip():
            doc_sections.append(
                f"=== {doc_path.name} ===\n{content}"
            )

    if not doc_sections:
        logger.warning("doc_analyzer: no documentation files found in %s", repo_path)
        return {
            "doc_context": {
                "feature_rationale": "Not documented.",
                "bug_stories": [],
                "tradeoffs": [],
                "evolution_notes": "Not documented.",
                "doc_quality": "low",
            },
        }

    logger.info("doc_analyzer: found %d documentation files", len(doc_sections))

    # ── Step 2: Ask Claude to extract narrative context ────────────────────────
    docs_combined = "\n\n".join(doc_sections)

    user_message = f"""Concept being studied: {concept_name}
Category: {state.get('category', '')}

Documentation files from the codebase:

{docs_combined}

Extract the narrative context as specified.""".strip()

    response = await call_llm(
        provider="anthropic",
        model=settings.default_research_model,
        system_prompt=_SYSTEM_PROMPT,
        user_message=user_message,
        temperature=0.0,
        max_tokens=2048,
    )

    raw = _strip_fences(response.content)
    try:
        doc_context = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("doc_analyzer: JSON parse failed: %s", exc)
        doc_context = {
            "feature_rationale": "Not documented.",
            "bug_stories": [],
            "tradeoffs": [],
            "evolution_notes": "Not documented.",
            "doc_quality": "low",
        }

    logger.info(
        "doc_analyzer: extracted %d bug stories, %d trade-offs (quality: %s)",
        len(doc_context.get("bug_stories", [])),
        len(doc_context.get("tradeoffs", [])),
        doc_context.get("doc_quality", "unknown"),
    )

    # Return ONLY the key this branch writes — parallel branch rule (see code_researcher).
    return {"doc_context": doc_context}


def _strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        parts = s.split("```")
        if len(parts) >= 3:
            s = parts[1]
            if s.startswith("json"):
                s = s[4:]
    return s.strip()
