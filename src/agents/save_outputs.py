"""
Save Outputs Node — Phase 3, final node.

Writes all generated content to disk. Runs as a graph node (rather than inline
in main.py) so the human-in-the-loop interrupt fires before files are written
when running in --interactive mode.

Input state fields used:
    output_path, concept_name, guide_html, linkedin_post, reel_script,
    teaching_plan, code_evidence, implementation_notes, doc_context,
    generalized_pattern, review_result, editor_result

Output state fields written:
    is_complete — True
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.state import PipelineState

logger = logging.getLogger(__name__)


async def save_outputs_node(state: PipelineState) -> dict:
    """
    LangGraph node: write all pipeline outputs to disk.
    """
    output_path = state.get("output_path", "")
    if not output_path:
        logger.error("save_outputs: no output_path in state — cannot write files")
        return {**state, "is_complete": False}

    out_root = Path(output_path)
    out_root.mkdir(parents=True, exist_ok=True)

    concept_name = state.get("concept_name", "")
    logger.info("save_outputs: writing files for '%s' → %s", concept_name, out_root)

    # ── Fact sheet ─────────────────────────────────────────────────────────────
    fact_sheet = {
        "concept_name": state.get("concept_name"),
        "category": state.get("category"),
        "why_it_matters": state.get("why_it_matters"),
        "repo_path": state.get("repo_path"),
        "teaching_plan": state.get("teaching_plan", {}),
        "code_evidence": state.get("code_evidence", []),
        "implementation_notes": state.get("implementation_notes", {}),
        "doc_context": state.get("doc_context", {}),
        "generalized_pattern": state.get("generalized_pattern", {}),
        "review_result": state.get("review_result", {}),
        "editor_result": state.get("editor_result", {}),
    }
    fact_sheet_path = out_root / "fact_sheet.json"
    fact_sheet_path.write_text(
        json.dumps(fact_sheet, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("save_outputs: wrote %s", fact_sheet_path)

    # ── guide.html ─────────────────────────────────────────────────────────────
    guide_html = state.get("guide_html", "")
    if guide_html:
        guide_path = out_root / "guide.html"
        guide_path.write_text(guide_html, encoding="utf-8")
        logger.info("save_outputs: wrote %s (%d chars)", guide_path, len(guide_html))

    # ── linkedin.md ────────────────────────────────────────────────────────────
    linkedin_post = state.get("linkedin_post", "")
    if linkedin_post:
        (out_root / "linkedin.md").write_text(linkedin_post, encoding="utf-8")

    # ── reel_script.md ─────────────────────────────────────────────────────────
    reel_script = state.get("reel_script", "")
    if reel_script:
        (out_root / "reel_script.md").write_text(reel_script, encoding="utf-8")

    return {**state, "is_complete": True}
