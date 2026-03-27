"""
LangGraph graph definition for the Peer Learning Content Factory pipeline.

Phase 2 graph (current):
    topic_parser
        ├──→ code_researcher  ─┐
        └──→ doc_analyzer     ─┤ (parallel)
                               ↓
                       concept_mapper → pedagogy_planner → writer → END

Phase 1 graph (superseded):
    topic_parser → code_researcher → END

Fan-out / fan-in:
    topic_parser fans out to code_researcher and doc_analyzer simultaneously.
    Both write to separate state keys (code_evidence/implementation_notes vs
    doc_context) so there are no parallel write conflicts.
    concept_mapper receives the merged state from both branches.

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
from src.agents.pedagogy_planner import pedagogy_planner_node
from src.agents.topic_parser import topic_parser_node
from src.agents.writer import writer_node
from src.state import PipelineState

logger = logging.getLogger(__name__)


def build_graph() -> StateGraph:
    """
    Construct and compile the Phase 2 pipeline graph.

    Phase 2 topology:
        START
          → topic_parser
          → [code_researcher ‖ doc_analyzer]   (parallel fan-out)
          → concept_mapper                      (fan-in — waits for both)
          → pedagogy_planner
          → writer
          → END
    """
    graph = StateGraph(PipelineState)

    # ── Register nodes ────────────────────────────────────────────────────────
    graph.add_node("topic_parser", topic_parser_node)
    graph.add_node("code_researcher", code_researcher_node)
    graph.add_node("doc_analyzer", doc_analyzer_node)
    graph.add_node("concept_mapper", concept_mapper_node)
    graph.add_node("pedagogy_planner", pedagogy_planner_node)
    graph.add_node("writer", writer_node)

    # ── Wire edges ────────────────────────────────────────────────────────────
    graph.add_edge(START, "topic_parser")

    # Fan-out: topic_parser → two parallel research branches
    graph.add_edge("topic_parser", "code_researcher")
    graph.add_edge("topic_parser", "doc_analyzer")

    # Fan-in: both branches → concept_mapper (waits for both to complete)
    graph.add_edge("code_researcher", "concept_mapper")
    graph.add_edge("doc_analyzer", "concept_mapper")

    # Linear pipeline after research is complete
    graph.add_edge("concept_mapper", "pedagogy_planner")
    graph.add_edge("pedagogy_planner", "writer")
    graph.add_edge("writer", END)

    return graph.compile()


# ── Phase 3+ expansion hooks (stubs) ──────────────────────────────────────────


def _add_phase3_nodes(graph: StateGraph) -> None:
    """
    Placeholder for Phase 3 nodes:
        linkedin_writer, reel_writer, diagram_generator (parallel with writer)
    These are currently handled inside writer.py as part of Phase 2.
    Phase 3 will extract them into dedicated nodes.
    """
    pass  # TODO: Phase 3


def _add_phase4_nodes(graph: StateGraph) -> None:
    """
    Placeholder for Phase 4 nodes:
        tech_reviewer → conditional: [writer retry | editor] → human checkpoint
    """
    pass  # TODO: Phase 4
