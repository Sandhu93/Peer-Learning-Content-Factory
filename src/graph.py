"""
LangGraph graph definition for the Peer Learning Content Factory pipeline.

Phase 4 graph (current):
    topic_parser
        ├──→ code_researcher  ─┐
        └──→ doc_analyzer     ─┤ (parallel fan-out / fan-in)
                               ↓
                       concept_mapper → pedagogy_planner → writer
                                                              ↓
                                           ┌──────────────────┼──────────────────┐
                                     linkedin_writer    reel_writer    diagram_generator
                                           └──────────────────┼──────────────────┘
                                                       (parallel fan-in)
                                                              ↓
                                                       tech_reviewer
                                                              ↓
                                              ┌── accurate / max retries ──→ editor → save_outputs → END
                                              └── not accurate ──→ increment_revision ──→ writer (retry loop)

Fan-out / fan-in (Phase 1 research):
    topic_parser fans out to code_researcher and doc_analyzer simultaneously.
    Both write to separate state keys, no parallel write conflicts.
    concept_mapper is the fan-in point.

Fan-out / fan-in (Phase 4 content variants):
    writer fans out to linkedin_writer, reel_writer, diagram_generator simultaneously.
    Each writes to a separate state key (linkedin_post / reel_script / diagram_svgs).
    tech_reviewer is the fan-in point — waits for all three to complete.

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
from src.agents.diagram_generator import diagram_generator_node
from src.agents.doc_analyzer import doc_analyzer_node
from src.agents.editor import editor_node
from src.agents.linkedin_writer import linkedin_writer_node
from src.agents.pedagogy_planner import pedagogy_planner_node
from src.agents.reel_writer import reel_writer_node
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
    Construct and compile the Phase 4 pipeline graph.

    Phase 4 topology:
        START
          → topic_parser
          → [code_researcher ‖ doc_analyzer]                     (parallel fan-out)
          → concept_mapper                                        (fan-in — waits for both)
          → pedagogy_planner
          → writer                                               (produces guide_html)
          → [linkedin_writer ‖ reel_writer ‖ diagram_generator]  (parallel fan-out)
          → tech_reviewer                                        (fan-in — waits for all three)
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
    graph.add_node("linkedin_writer", linkedin_writer_node)
    graph.add_node("reel_writer", reel_writer_node)
    graph.add_node("diagram_generator", diagram_generator_node)
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

    # ── Phase 4 edges — content variant fan-out ────────────────────────────────
    # Fan-out: writer → three parallel content variant branches
    graph.add_edge("writer", "linkedin_writer")
    graph.add_edge("writer", "reel_writer")
    graph.add_edge("writer", "diagram_generator")

    # Fan-in: all three content variants → tech_reviewer (waits for all three)
    graph.add_edge("linkedin_writer", "tech_reviewer")
    graph.add_edge("reel_writer", "tech_reviewer")
    graph.add_edge("diagram_generator", "tech_reviewer")

    # ── Phase 3 edges ──────────────────────────────────────────────────────────
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
