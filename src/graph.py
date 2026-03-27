"""
LangGraph graph definition for the Peer Learning Content Factory pipeline.

Phase 1 graph (current):
    topic_parser → code_researcher → END

The graph is designed for incremental expansion — later phases add
doc_analyzer, concept_mapper, pedagogy_planner, writer, reviewer, editor
nodes with conditional edges and human-in-the-loop checkpoints.

Usage:
    from src.graph import build_graph

    graph = build_graph()
    result = await graph.ainvoke({
        "concept_name": "Circuit breaker for provider failure",
        "category": "Reliability, Failure Isolation, and Production Hardening",
        "why_it_matters": "...",
        "repo_anchors": ["circuit_breaker", "CircuitBreaker"],
    })
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from src.agents.code_researcher import code_researcher_node
from src.agents.topic_parser import topic_parser_node
from src.state import PipelineState

logger = logging.getLogger(__name__)


def build_graph() -> StateGraph:
    """
    Construct and compile the Phase 1 pipeline graph.

    Phase 1 topology:
        START → topic_parser → code_researcher → END
    """
    graph = StateGraph(PipelineState)

    # ── Register nodes ────────────────────────────────────────────────────────
    graph.add_node("topic_parser", topic_parser_node)
    graph.add_node("code_researcher", code_researcher_node)

    # ── Wire edges ────────────────────────────────────────────────────────────
    graph.add_edge(START, "topic_parser")
    graph.add_edge("topic_parser", "code_researcher")
    graph.add_edge("code_researcher", END)

    return graph.compile()


# ── Phase 2+ expansion hooks (stubs) ──────────────────────────────────────────
# These are imported lazily when Phase 2 nodes are ready so the graph can be
# extended without touching the Phase 1 wiring.

def _add_phase2_nodes(graph: StateGraph) -> None:
    """
    Placeholder for Phase 2 nodes:
        doc_analyzer, concept_mapper (parallel with code_researcher),
        pedagogy_planner → writer
    """
    pass  # TODO: Phase 2


def _add_phase3_nodes(graph: StateGraph) -> None:
    """
    Placeholder for Phase 3 nodes:
        linkedin_writer, reel_writer, diagram_generator (parallel with writer)
    """
    pass  # TODO: Phase 3


def _add_phase4_nodes(graph: StateGraph) -> None:
    """
    Placeholder for Phase 4 nodes:
        tech_reviewer → conditional: [writer retry | editor] → human checkpoint
    """
    pass  # TODO: Phase 4
