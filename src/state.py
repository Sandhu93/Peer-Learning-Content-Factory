"""
LangGraph state schema for the Peer Learning Content Factory pipeline.

The single PipelineState TypedDict flows through every node in the graph.
Each agent reads what it needs and writes to its designated output fields.
"""

from __future__ import annotations

from typing import Optional, TypedDict

from pydantic import BaseModel


# ── Sub-models (used inside PipelineState lists) ──────────────────────────────


class CodeSnippet(BaseModel):
    """A relevant excerpt from the target codebase."""

    file_path: str
    line_start: int
    line_end: int
    content: str
    relevance: str  # one-sentence explanation of why this is relevant


class BugStory(BaseModel):
    """A production bug that illustrates the concept."""

    title: str
    symptom: str       # what the user/operator observed
    root_cause: str    # underlying technical cause
    fix: str           # what change was made
    lesson: str        # generalizable takeaway


class DiagramSpec(BaseModel):
    """
    Declarative specification for a diagram.
    The diagram_generator agent renders this to SVG.
    """

    diagram_type: str           # "state_machine" | "architecture" | "flowchart" | "comparison"
    title: str
    nodes: list[dict]           # {id, label, subtitle?, color}
    edges: list[dict]           # {from_id, to_id, label?, style?}


# ── Main pipeline state ───────────────────────────────────────────────────────


class PipelineState(TypedDict, total=False):
    # ── Input (set by CLI / topic_parser) ─────────────────────────────────────
    concept_name: str
    category: str
    why_it_matters: str
    repo_anchors: list[str]

    # ── Research outputs ───────────────────────────────────────────────────────
    code_evidence: list[dict]       # list of CodeSnippet.model_dump()
    doc_context: dict               # {feature_rationale, bug_stories[], tradeoffs[], evolution_notes}
    generalized_pattern: dict       # {pattern_name, general_description, naive_approach,
    #                                  why_naive_fails, production_approach,
    #                                  applicable_domains[], anti_patterns[]}

    # ── Planning ──────────────────────────────────────────────────────────────
    teaching_plan: dict             # {difficulty, sections_to_include[], diagram_types[],
    #                                  comparison_type, code_example_strategy}
    diagram_specs: list[dict]       # list of DiagramSpec.model_dump()

    # ── Content drafts ────────────────────────────────────────────────────────
    guide_html: str
    linkedin_post: str
    reel_script: str
    diagram_svgs: list[str]         # parallel list matching diagram_specs order

    # ── Review ────────────────────────────────────────────────────────────────
    review_result: dict             # {is_accurate: bool, corrections[], suggestions[]}
    editor_result: dict             # {changes_made: bool, notes[]}
    revision_count: int

    # ── Human-in-the-loop ────────────────────────────────────────────────────
    human_feedback: Optional[str]   # set when running in --interactive mode

    # ── Control ───────────────────────────────────────────────────────────────
    is_complete: bool
    output_path: str
    errors: list[str]               # accumulated non-fatal error messages
