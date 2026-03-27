"""
Writer Agent — Phase 2, Node 5.

Takes the complete fact sheet (research + plan) and produces the filled
HTML guide, LinkedIn post, and reel script.

Responsibilities:
  1. Render SVG diagrams from diagram_specs using svg_builder
  2. Call Claude with all research context to generate content JSON
  3. Fill the frozen HTML template with the generated content + diagrams

Input state fields used:
    concept_name, category, why_it_matters,
    code_evidence, implementation_notes, doc_context, generalized_pattern,
    teaching_plan, diagram_specs

Output state fields written:
    guide_html, linkedin_post, reel_script, diagram_svgs
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.state import PipelineState
from src.utils.llm import call_llm
from src.utils.svg_builder import SVGCanvas, create_state_machine

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "writer.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

_TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "guide_template.html"
_TEMPLATE = _TEMPLATE_PATH.read_text(encoding="utf-8")

_MAX_EVIDENCE_IN_PROMPT = 6


async def writer_node(state: PipelineState) -> PipelineState:
    """
    LangGraph node: generate the complete HTML guide.
    """
    from src.config import settings

    concept_name = state["concept_name"]
    logger.info("writer: generating guide for '%s'", concept_name)

    # ── Step 1: Render diagrams from pedagogy_planner specs ───────────────────
    diagram_specs = state.get("diagram_specs", [])
    rendered_svgs: dict[str, str] = {}   # placement → svg string
    svg_list: list[str] = []

    for spec in diagram_specs:
        svg = _render_diagram(spec)
        placement = spec.get("placement", "main")
        rendered_svgs[placement] = svg
        svg_list.append(svg)

    # Ensure we always have both diagram slots (use a minimal fallback)
    if "problem" not in rendered_svgs:
        rendered_svgs["problem"] = _fallback_svg("Problem Scenario")
    if "main" not in rendered_svgs:
        rendered_svgs["main"] = _fallback_svg("Solution Architecture")

    # ── Step 2: Build the prompt context ──────────────────────────────────────
    teaching_plan = state.get("teaching_plan", {})
    generalized_pattern = state.get("generalized_pattern", {})
    doc_context = state.get("doc_context", {})
    implementation_notes = state.get("implementation_notes", {})
    code_evidence = state.get("code_evidence", [])

    user_message = _build_user_message(
        state=state,
        teaching_plan=teaching_plan,
        generalized_pattern=generalized_pattern,
        doc_context=doc_context,
        implementation_notes=implementation_notes,
        code_evidence=code_evidence[:_MAX_EVIDENCE_IN_PROMPT],
    )

    # ── Step 3: Call Claude to produce content JSON ────────────────────────────
    response = await call_llm(
        provider="anthropic",
        model=settings.default_writer_model,
        system_prompt=_SYSTEM_PROMPT,
        user_message=user_message,
        temperature=0.3,
        max_tokens=8192,
    )

    raw = _strip_fences(response.content)
    try:
        content = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("writer: JSON parse failed: %s", exc)
        content = _empty_content(state)

    # ── Step 4: Fill the HTML template ────────────────────────────────────────
    guide_html = _fill_template(content, state, rendered_svgs, teaching_plan)

    linkedin_post = content.get("linkedin_post", "")
    reel_script = _format_reel_script(content.get("reel_scenes", []))

    logger.info("writer: guide generated (%d chars)", len(guide_html))

    return {
        **state,
        "guide_html": guide_html,
        "linkedin_post": linkedin_post,
        "reel_script": reel_script,
        "diagram_svgs": svg_list,
    }


# ── Diagram rendering ─────────────────────────────────────────────────────────


def _render_diagram(spec: dict) -> str:
    """Convert a DiagramSpec dict to an inline SVG string."""
    nodes = spec.get("nodes", [])
    edges = spec.get("edges", [])

    if not nodes:
        return _fallback_svg(spec.get("title", "Diagram"))

    # All diagram types use the same node/edge renderer (it's a general graph)
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


# ── Template filling ──────────────────────────────────────────────────────────


def _fill_template(
    content: dict,
    state: PipelineState,
    svgs: dict[str, str],
    teaching_plan: dict,
) -> str:
    """Substitute all {{variable}} placeholders in the template."""
    html = _TEMPLATE

    # Simple scalar substitutions
    scalars = {
        "concept_name":   state.get("concept_name", ""),
        "category":       state.get("category", ""),
        "why_it_matters": state.get("why_it_matters", ""),
        "difficulty":     teaching_plan.get("difficulty", "intermediate"),

        "problem_statement":   content.get("problem_statement", ""),
        "problem_context":     content.get("problem_context", ""),
        "problem_elaboration": content.get("problem_elaboration", ""),

        "naive_description": content.get("naive_description", ""),
        "naive_code":        content.get("naive_code", ""),
        "naive_failure":     content.get("naive_failure", ""),
        "prod_description":  content.get("prod_description", ""),
        "prod_code":         content.get("prod_code", ""),
        "prod_rationale":    content.get("prod_rationale", ""),

        "how_it_works_intro":   content.get("how_it_works_intro", ""),
        "subsection_1_title":   content.get("subsection_1_title", ""),
        "subsection_1_content": content.get("subsection_1_content", ""),
        "subsection_2_title":   content.get("subsection_2_title", ""),
        "subsection_2_content": content.get("subsection_2_content", ""),
        "key_insight":          content.get("key_insight", ""),

        "code_intro":                   content.get("code_intro", ""),
        "code_file_ref_1":              content.get("code_file_ref_1", ""),
        "code_snippet_1":               content.get("code_snippet_1", ""),
        "code_snippet_1_explanation":   content.get("code_snippet_1_explanation", ""),
        "code_file_ref_2":              content.get("code_file_ref_2", ""),
        "code_snippet_2":               content.get("code_snippet_2", ""),
        "code_snippet_2_explanation":   content.get("code_snippet_2_explanation", ""),

        "bug_title":      content.get("bug_title", ""),
        "bug_symptom":    content.get("bug_symptom", ""),
        "bug_root_cause": content.get("bug_root_cause", ""),
        "bug_fix":        content.get("bug_fix", ""),
        "bug_lesson":     content.get("bug_lesson", ""),

        "tradeoffs_intro": content.get("tradeoffs_intro", ""),
        "anti_patterns":   content.get("anti_patterns", ""),

        # SVGs
        "diagram_problem":         svgs.get("problem", ""),
        "diagram_problem_caption": _diagram_caption(state.get("diagram_specs", []), "problem"),
        "diagram_main":            svgs.get("main", ""),
        "diagram_main_caption":    _diagram_caption(state.get("diagram_specs", []), "main"),

        # LinkedIn
        "linkedin_post":        content.get("linkedin_post", ""),
        "linkedin_char_count":  str(len(content.get("linkedin_post", ""))),
    }

    for key, value in scalars.items():
        html = html.replace("{{" + key + "}}", str(value))

    # List substitutions (arrays → HTML fragments)
    use_when_html = "".join(f"<li>{_esc(item)}</li>" for item in content.get("use_when_items", []))
    avoid_when_html = "".join(f"<li>{_esc(item)}</li>" for item in content.get("avoid_when_items", []))
    html = html.replace("{{use_when_list}}", use_when_html)
    html = html.replace("{{avoid_when_list}}", avoid_when_html)

    prompts_html = "".join(
        f'<div class="prompt-item">{_esc(p)}</div>'
        for p in content.get("discussion_prompts", [])
    )
    html = html.replace("{{discussion_prompt_items}}", prompts_html)

    reel_html = _render_reel_scenes(content.get("reel_scenes", []))
    html = html.replace("{{reel_scenes}}", reel_html)

    pills_html = "".join(
        f'<a class="topic-pill" href="#">{_esc(t)}</a>'
        for t in content.get("related_topics", [])
    )
    html = html.replace("{{related_topic_pills}}", pills_html)

    return html


def _diagram_caption(specs: list[dict], placement: str) -> str:
    for spec in specs:
        if spec.get("placement") == placement:
            return spec.get("title", "")
    return ""


def _render_reel_scenes(scenes: list[dict]) -> str:
    if not scenes:
        return ""
    parts = []
    for scene in scenes:
        ts = _esc(scene.get("timestamp", ""))
        title = _esc(scene.get("title", ""))
        visual = _esc(scene.get("visual", ""))
        script = _esc(scene.get("script", ""))
        parts.append(
            f'<div class="reel-scene">'
            f'<div class="scene-timestamp">{ts}</div>'
            f'<div class="scene-content">'
            f'<div class="scene-title">{title}</div>'
            f'<div class="scene-visual">{visual}</div>'
            f"<p>{script}</p>"
            f"</div></div>"
        )
    return "\n".join(parts)


def _format_reel_script(scenes: list[dict]) -> str:
    """Plain-text version of the reel script for reel_script.md."""
    if not scenes:
        return ""
    lines = []
    for scene in scenes:
        lines.append(f"[{scene.get('timestamp', '')}] {scene.get('title', '')}")
        lines.append(f"Visual: {scene.get('visual', '')}")
        lines.append(scene.get("script", ""))
        lines.append("")
    return "\n".join(lines)


# ── User message builder ──────────────────────────────────────────────────────


def _build_user_message(
    state: PipelineState,
    teaching_plan: dict,
    generalized_pattern: dict,
    doc_context: dict,
    implementation_notes: dict,
    code_evidence: list[dict],
) -> str:
    evidence_text = _format_evidence(code_evidence)
    bug_stories_text = _format_bug_stories(doc_context.get("bug_stories", []))

    return f"""CONCEPT: {state.get('concept_name', '')}
CATEGORY: {state.get('category', '')}
WHY IT MATTERS: {state.get('why_it_matters', '')}
DIFFICULTY: {teaching_plan.get('difficulty', 'intermediate')}

HOOK (use as opening framing):
{teaching_plan.get('hook', '')}

ANALOGY (use to explain the concept):
{teaching_plan.get('analogy', '')}

COMPARISON FRAMING (for naive/production card headers):
{teaching_plan.get('comparison_framing', 'Naive Approach vs Production Solution')}

CODE EXAMPLE STRATEGY:
{teaching_plan.get('code_example_strategy', 'Show the most illustrative implementation snippets.')}

GENERALIZED PATTERN:
{json.dumps(generalized_pattern, indent=2)}

IMPLEMENTATION SUMMARY (repo-specific):
{implementation_notes.get('implementation_summary', '(not available)')}

CODE EVIDENCE (use verbatim for code_snippet_1 and code_snippet_2):
{evidence_text}

FEATURE RATIONALE (from docs):
{doc_context.get('feature_rationale', '(not available)')}

BUG STORIES (use the first one for the bug story section):
{bug_stories_text}

TRADE-OFFS (use in tradeoffs section):
{chr(10).join('- ' + t for t in doc_context.get('tradeoffs', []))}

DISCUSSION PROMPTS (use these exactly):
{chr(10).join(f'{i+1}. {p}' for i, p in enumerate(teaching_plan.get('discussion_prompts', [])))}

RELATED CONCEPTS (use for related_topics):
{', '.join(teaching_plan.get('related_concepts', [])[:5])}

Produce the complete guide content JSON as specified.""".strip()


def _format_evidence(evidence: list[dict]) -> str:
    if not evidence:
        return "(no code evidence available)"
    parts = []
    for e in evidence:
        parts.append(
            f"FILE: {e.get('file_path', '?')} "
            f"(lines {e.get('line_start', '?')}–{e.get('line_end', '?')})\n"
            f"RELEVANCE: {e.get('relevance', '')}\n"
            f"```\n{e.get('content', '')}\n```"
        )
    return "\n\n".join(parts)


def _format_bug_stories(stories: list[dict]) -> str:
    if not stories:
        return "(no bug stories documented — construct a teaching scenario based on the concept)"
    parts = []
    for s in stories:
        parts.append(
            f"Title: {s.get('title', '')}\n"
            f"Symptom: {s.get('symptom', '')}\n"
            f"Root cause: {s.get('root_cause', '')}\n"
            f"Fix: {s.get('fix', '')}\n"
            f"Lesson: {s.get('lesson', '')}"
        )
    return "\n\n".join(parts)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _esc(s: str) -> str:
    """Escape HTML special characters for safe template injection."""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        parts = s.split("```")
        if len(parts) >= 3:
            s = parts[1]
            if s.startswith("json"):
                s = s[4:]
    return s.strip()


def _empty_content(state: PipelineState) -> dict:
    """Minimal fallback content so the template renders without crashing."""
    name = state.get("concept_name", "")
    return {
        "problem_statement": f"Without {name}, production systems face reliability issues.",
        "problem_context": "", "problem_elaboration": "",
        "naive_description": "", "naive_code": "# (content generation failed)",
        "naive_failure": "", "prod_description": "",
        "prod_code": "# (content generation failed)", "prod_rationale": "",
        "how_it_works_intro": "", "subsection_1_title": "Overview",
        "subsection_1_content": "", "subsection_2_title": "Configuration",
        "subsection_2_content": "", "key_insight": "",
        "code_intro": "", "code_file_ref_1": "", "code_snippet_1": "",
        "code_snippet_1_explanation": "", "code_file_ref_2": "",
        "code_snippet_2": "", "code_snippet_2_explanation": "",
        "bug_title": "", "bug_symptom": "", "bug_root_cause": "",
        "bug_fix": "", "bug_lesson": "",
        "tradeoffs_intro": "", "use_when_items": [], "avoid_when_items": [],
        "anti_patterns": "", "discussion_prompts": [],
        "linkedin_post": "", "reel_scenes": [], "related_topics": [],
    }
