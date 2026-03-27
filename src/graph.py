"""
LangGraph graph definition for the Peer Learning Content Factory pipeline.

Phase 3 graph (current):
    topic_parser
        ├──→ code_researcher  ─┐
        └──→ doc_analyzer     ─┤ (parallel)
                               ↓
                       concept_mapper → pedagogy_planner → writer
                                                              ↓
                                                       tech_reviewer
                                                              ↓
                                              ┌── accurate / max retries ──→ editor → save_outputs → END
                                              └── not accurate ──→ increment_revision ──→ writer (retry loop)

Fan-out / fan-in:
    topic_parser fans out to code_researcher and doc_analyzer simultaneously.
    Both write to separate state keys (code_evidence/implementation_notes vs
    doc_context) so there are no parallel write conflicts.
    concept_mapper receives the merged state from both branches.

Interactive mode:
    Pass interactive=True to compile with interrupt_before=["save_outputs"].
    The graph pauses before writing files, allowing human review/approval.

Usage:
    from src.graph import build_graph

    graph = build_graph()
    result = await graph.ainvoke(initial_state)
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from src.agents.code_researcher import code_researcher_node
from src.agents.concept_mapper import concept_mapper_node
from src.agents.doc_analyzer import doc_analyzer_node
from src.agents.editor import editor_node
from src.agents.pedagogy_planner import pedagogy_planner_node
from src.agents.save_outputs import save_outputs_node
from src.agents.tech_reviewer import tech_reviewer_node
from src.agents.topic_parser import topic_parser_node
from src.agents.writer import writer_node
from src.state import PipelineState

logger = logging.getLogger(__name__)


def _route_after_review(state: PipelineState) -> str:
    """
    Conditional edge after tech_reviewer.

    Routes to:
      - "editor"            if the guide is accurate, or if max revisions reached
      - "increment_revision" if inaccurate and retries remain
    """
    from src.config import settings

    review_result = state.get("review_result", {})
    is_accurate = review_result.get("is_accurate", True)
    revision_count = state.get("revision_count", 0)

    if is_accurate:
        logger.info("tech_reviewer: guide is accurate — forwarding to editor")
        return "editor"

    if revision_count >= settings.max_revisions:
        logger.warning(
            "tech_reviewer: max revisions (%d) reached — forwarding to editor anyway",
            settings.max_revisions,
        )
        return "editor"

    logger.info(
        "tech_reviewer: inaccuracies found (revision %d/%d) — sending back to writer",
        revision_count + 1,
        settings.max_revisions,
    )
    return "increment_revision"


async def _increment_revision_node(state: PipelineState) -> dict:
    """Thin node: bump revision_count before sending back to writer."""
    new_count = state.get("revision_count", 0) + 1
    logger.info("increment_revision: revision_count → %d", new_count)
    return {**state, "revision_count": new_count}


def build_graph(interactive: bool = False):
    """
    Construct and compile the Phase 3 pipeline graph.

    Phase 3 topology:
        START
          → topic_parser
          → [code_researcher ‖ doc_analyzer]   (parallel fan-out)
          → concept_mapper                      (fan-in — waits for both)
          → pedagogy_planner
          → writer
          → tech_reviewer
          → [_route_after_review]
              ├── "editor"             → editor → save_outputs → END
              └── "increment_revision" → increment_revision → writer (retry loop)

    Args:
        interactive: If True, compile with interrupt_before=["save_outputs"] and a
                     MemorySaver checkpointer so the graph can be paused for human review.
    """
    graph = StateGraph(PipelineState)

    # ── Register nodes ─────────────────────────────────────────────────────────
    graph.add_node("topic_parser", topic_parser_node)
    graph.add_node("code_researcher", code_researcher_node)
    graph.add_node("doc_analyzer", doc_analyzer_node)
    graph.add_node("concept_mapper", concept_mapper_node)
    graph.add_node("pedagogy_planner", pedagogy_planner_node)
    graph.add_node("writer", writer_node)
    graph.add_node("tech_reviewer", tech_reviewer_node)
    graph.add_node("increment_revision", _increment_revision_node)
    graph.add_node("editor", editor_node)
    graph.add_node("save_outputs", save_outputs_node)

    # ── Phase 1 + 2 edges ─────────────────────────────────────────────────────
    graph.add_edge(START, "topic_parser")

    # Fan-out: topic_parser → two parallel research branches
    graph.add_edge("topic_parser", "code_researcher")
    graph.add_edge("topic_parser", "doc_analyzer")

    # Fan-in: both branches → concept_mapper (waits for both to complete)
    graph.add_edge("code_researcher", "concept_mapper")
    graph.add_edge("doc_analyzer", "concept_mapper")

    graph.add_edge("concept_mapper", "pedagogy_planner")
    graph.add_edge("pedagogy_planner", "writer")

    # ── Phase 3 edges ──────────────────────────────────────────────────────────
    graph.add_edge("writer", "tech_reviewer")

    graph.add_conditional_edges(
        "tech_reviewer",
        _route_after_review,
        {"editor": "editor", "increment_revision": "increment_revision"},
    )

    # Revision retry loop: increment_revision → writer
    graph.add_edge("increment_revision", "writer")

    # Happy path: editor → save_outputs → END
    graph.add_edge("editor", "save_outputs")
    graph.add_edge("save_outputs", END)

    # ── Compile ────────────────────────────────────────────────────────────────
    if interactive:
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()
        return graph.compile(
            checkpointer=checkpointer,
            interrupt_before=["save_outputs"],
        )

    return graph.compile()
