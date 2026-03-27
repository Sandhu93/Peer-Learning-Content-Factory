"""
Diagram Generator — Phase 4, Content Variant Node.

Pure Python — no LLM call. Renders diagram_specs (produced by pedagogy_planner)
into standalone SVG strings. Runs in parallel with linkedin_writer and reel_writer
after the writer node completes.

Input state fields used:
    diagram_specs — list[DiagramSpec.model_dump()]

Output state fields written:
    diagram_svgs — list[str]  (parallel list matching diagram_specs order)
"""

from __future__ import annotations

import logging

from src.state import PipelineState
from src.utils.svg_builder import SVGCanvas, create_state_machine

logger = logging.getLogger(__name__)


async def diagram_generator_node(state: PipelineState) -> dict:
    """
    LangGraph node: render all diagram_specs to SVG strings.

    Returns only diagram_svgs (ADR-010 — parallel node owns only its key).
    """
    diagram_specs = state.get("diagram_specs", [])
    concept_name = state.get("concept_name", "")

    logger.info(
        "diagram_generator: rendering %d diagram(s) for '%s'",
        len(diagram_specs),
        concept_name,
    )

    svg_list: list[str] = []
    for spec in diagram_specs:
        svg = _render_diagram(spec)
        svg_list.append(svg)

    logger.info("diagram_generator: rendered %d SVG(s)", len(svg_list))

    # ADR-010: return only owned keys — LangGraph merges with state from other
    # parallel branches (linkedin_writer, reel_writer) before tech_reviewer runs.
    return {"diagram_svgs": svg_list}


# ── Rendering helpers ─────────────────────────────────────────────────────────


def _render_diagram(spec: dict) -> str:
    """Convert a DiagramSpec dict to an inline SVG string."""
    nodes = spec.get("nodes", [])
    edges = spec.get("edges", [])

    if not nodes:
        return _fallback_svg(spec.get("title", "Diagram"))

    return create_state_machine(
        states=nodes,
        transitions=edges,
        width=640,
        height=260,
    )


def _fallback_svg(title: str) -> str:
    """Minimal placeholder SVG when no spec is available."""
    canvas = SVGCanvas(640, 120)
    canvas.add_text(320, 55, title, size=15, bold=True, color="var(--text-muted)")
    canvas.add_text(320, 80, "(diagram not generated)", size=11, color="var(--text-subtle)")
    return canvas.render()
