"""
Unit tests for writer.py rendering helpers (no LLM calls).

Tests the pure-Python parts of the writer:
  - _fill_template: all placeholders replaced, HTML structure intact
  - _render_reel_scenes: correct div structure
  - _render_diagram: SVG produced from DiagramSpec
  - _fallback_svg: valid SVG when no spec available
  - _esc: HTML special character escaping in injected content
  - list items (use_when, avoid_when, discussion_prompts): correct HTML fragments
"""

from __future__ import annotations

import re

import pytest

from src.agents.writer import (
    _esc,
    _fallback_svg,
    _fill_template,
    _render_diagram,
    _render_reel_scenes,
)

# Minimal complete content dict — all keys that _fill_template references
_MINIMAL_CONTENT = {
    "problem_statement": "Without circuit breaker, slow provider exhausts thread pool.",
    "problem_context": "Context paragraph.",
    "problem_elaboration": "Elaboration paragraph.",
    "naive_description": "Call provider in a retry loop.",
    "naive_code": "for i in range(3):\n    client.call()",
    "naive_failure": "Threads block on 45s timeouts.",
    "prod_description": "Wrap call in circuit breaker.",
    "prod_code": "if self.state == State.OPEN:\n    raise CircuitOpenError()",
    "prod_rationale": "Fails fast when OPEN.",
    "how_it_works_intro": "The circuit breaker is a three-state proxy.",
    "subsection_1_title": "State Transitions",
    "subsection_1_content": "CLOSED → OPEN after threshold failures.",
    "subsection_2_title": "Recovery Protocol",
    "subsection_2_content": "OPEN → HALF_OPEN after timeout.",
    "key_insight": "It opens to protect the caller.",
    "code_intro": "Here is the core implementation.",
    "code_file_ref_1": "circuit_breaker.py:10-14",
    "code_snippet_1": "class State(Enum):\n    CLOSED = 'closed'",
    "code_snippet_1_explanation": "Three state enum.",
    "code_file_ref_2": "circuit_breaker.py:50-58",
    "code_snippet_2": "def _on_failure(self):\n    self._failure_count += 1",
    "code_snippet_2_explanation": "Failure counter logic.",
    "bug_title": "March 2024 Outage",
    "bug_symptom": "Queries timed out for 8 minutes.",
    "bug_root_cause": "Retry loop exhausted thread pool.",
    "bug_fix": "Added CircuitBreaker.",
    "bug_lesson": "Retries without circuit breaking cause cascading failures.",
    "tradeoffs_intro": "Configuration involves explicit trade-offs.",
    "use_when_items": ["Calling unreliable external APIs", "High-throughput services"],
    "avoid_when_items": ["Internal calls", "Must-complete operations"],
    "anti_patterns": "Forgetting HALF_OPEN prevents recovery.",
    "discussion_prompts": [
        "How would you choose the threshold?",
        "What if HALF_OPEN probe itself times out?",
        "When would this cause more harm?",
        "How to test without mocking time?",
    ],
    "linkedin_post": "Your service was down.\n\nNot because the provider failed.",
    "reel_scenes": [
        {"timestamp": "0:00-0:05", "title": "Hook", "visual": "[text]", "script": "Your service is down."},
        {"timestamp": "0:05-0:15", "title": "Problem", "visual": "[diagram]", "script": "Slow provider blocks all threads."},
        {"timestamp": "0:15-0:25", "title": "Naive", "visual": "[code]", "script": "The naive fix: more retries."},
        {"timestamp": "0:25-0:40", "title": "Solution", "visual": "[state machine]", "script": "Circuit breaker: three states."},
        {"timestamp": "0:40-0:50", "title": "Insight", "visual": "[callout]", "script": "It opens to protect the caller."},
        {"timestamp": "0:50-0:60", "title": "CTA", "visual": "[text]", "script": "Which service needs this first?"},
    ],
    "related_topics": ["Retry with exponential backoff", "Bulkhead pattern", "Timeout budgets"],
}

_MINIMAL_STATE = {
    "concept_name": "Circuit breaker for provider failure",
    "category": "Reliability, Failure Isolation, and Production Hardening",
    "why_it_matters": "Prevents cascading failures.",
    "diagram_specs": [],
}

_MINIMAL_TEACHING_PLAN = {"difficulty": "intermediate"}

_MINIMAL_SVGS = {
    "problem": "<svg viewBox='0 0 640 260'><text>problem</text></svg>",
    "main": "<svg viewBox='0 0 640 260'><text>main</text></svg>",
}


class TestFillTemplate:
    def test_no_unfilled_placeholders(self):
        html = _fill_template(_MINIMAL_CONTENT, _MINIMAL_STATE, _MINIMAL_SVGS, _MINIMAL_TEACHING_PLAN)
        remaining = re.findall(r"\{\{[^}]+\}\}", html)
        assert remaining == [], f"Unfilled: {remaining}"

    def test_concept_name_in_title_tag(self):
        html = _fill_template(_MINIMAL_CONTENT, _MINIMAL_STATE, _MINIMAL_SVGS, _MINIMAL_TEACHING_PLAN)
        assert "<title>Circuit breaker for provider failure" in html

    def test_concept_name_in_h1(self):
        html = _fill_template(_MINIMAL_CONTENT, _MINIMAL_STATE, _MINIMAL_SVGS, _MINIMAL_TEACHING_PLAN)
        assert "<h1>Circuit breaker for provider failure</h1>" in html

    def test_category_in_badge(self):
        html = _fill_template(_MINIMAL_CONTENT, _MINIMAL_STATE, _MINIMAL_SVGS, _MINIMAL_TEACHING_PLAN)
        assert "Reliability" in html

    def test_difficulty_in_meta_pill(self):
        html = _fill_template(_MINIMAL_CONTENT, _MINIMAL_STATE, _MINIMAL_SVGS, _MINIMAL_TEACHING_PLAN)
        assert "intermediate" in html

    def test_problem_statement_present(self):
        html = _fill_template(_MINIMAL_CONTENT, _MINIMAL_STATE, _MINIMAL_SVGS, _MINIMAL_TEACHING_PLAN)
        assert "slow provider exhausts thread pool" in html

    def test_code_snippet_1_present(self):
        html = _fill_template(_MINIMAL_CONTENT, _MINIMAL_STATE, _MINIMAL_SVGS, _MINIMAL_TEACHING_PLAN)
        assert "class State(Enum)" in html

    def test_bug_title_present(self):
        html = _fill_template(_MINIMAL_CONTENT, _MINIMAL_STATE, _MINIMAL_SVGS, _MINIMAL_TEACHING_PLAN)
        assert "March 2024 Outage" in html

    def test_use_when_items_rendered_as_li(self):
        html = _fill_template(_MINIMAL_CONTENT, _MINIMAL_STATE, _MINIMAL_SVGS, _MINIMAL_TEACHING_PLAN)
        assert "<li>Calling unreliable external APIs</li>" in html
        assert "<li>High-throughput services</li>" in html

    def test_avoid_when_items_rendered_as_li(self):
        html = _fill_template(_MINIMAL_CONTENT, _MINIMAL_STATE, _MINIMAL_SVGS, _MINIMAL_TEACHING_PLAN)
        assert "<li>Internal calls</li>" in html

    def test_discussion_prompts_rendered_with_class(self):
        html = _fill_template(_MINIMAL_CONTENT, _MINIMAL_STATE, _MINIMAL_SVGS, _MINIMAL_TEACHING_PLAN)
        assert 'class="prompt-item"' in html
        assert "How would you choose the threshold?" in html

    def test_four_discussion_prompts_rendered(self):
        html = _fill_template(_MINIMAL_CONTENT, _MINIMAL_STATE, _MINIMAL_SVGS, _MINIMAL_TEACHING_PLAN)
        count = html.count('class="prompt-item"')
        assert count == 4

    def test_linkedin_char_count_calculated(self):
        html = _fill_template(_MINIMAL_CONTENT, _MINIMAL_STATE, _MINIMAL_SVGS, _MINIMAL_TEACHING_PLAN)
        expected = str(len(_MINIMAL_CONTENT["linkedin_post"]))
        assert expected in html

    def test_reel_scenes_rendered(self):
        html = _fill_template(_MINIMAL_CONTENT, _MINIMAL_STATE, _MINIMAL_SVGS, _MINIMAL_TEACHING_PLAN)
        assert 'class="reel-scene"' in html
        assert "0:00-0:05" in html

    def test_related_topics_rendered_as_pills(self):
        html = _fill_template(_MINIMAL_CONTENT, _MINIMAL_STATE, _MINIMAL_SVGS, _MINIMAL_TEACHING_PLAN)
        assert 'class="topic-pill"' in html
        assert "Retry with exponential backoff" in html

    def test_problem_diagram_svg_injected(self):
        html = _fill_template(_MINIMAL_CONTENT, _MINIMAL_STATE, _MINIMAL_SVGS, _MINIMAL_TEACHING_PLAN)
        assert "<svg" in html
        assert "viewBox" in html

    def test_empty_use_when_items_produces_no_li(self):
        content = {**_MINIMAL_CONTENT, "use_when_items": []}
        html = _fill_template(content, _MINIMAL_STATE, _MINIMAL_SVGS, _MINIMAL_TEACHING_PLAN)
        # No crash; list section just empty
        assert "{{use_when_list}}" not in html

    def test_missing_content_key_produces_empty_string(self):
        content = {**_MINIMAL_CONTENT}
        del content["key_insight"]
        html = _fill_template(content, _MINIMAL_STATE, _MINIMAL_SVGS, _MINIMAL_TEACHING_PLAN)
        assert "{{key_insight}}" not in html


class TestHTMLEscapingInListItems:
    def test_html_special_chars_in_use_when_are_escaped(self):
        """User-controlled content in list items must not break HTML."""
        content = {**_MINIMAL_CONTENT, "use_when_items": ['<script>alert("xss")</script>']}
        html = _fill_template(content, _MINIMAL_STATE, _MINIMAL_SVGS, _MINIMAL_TEACHING_PLAN)
        # The template itself has <script> tags for JS — check the XSS payload is escaped
        assert '<script>alert' not in html
        assert "&lt;script&gt;" in html

    def test_ampersand_in_list_item_escaped(self):
        content = {**_MINIMAL_CONTENT, "use_when_items": ["A & B conditions"]}
        html = _fill_template(content, _MINIMAL_STATE, _MINIMAL_SVGS, _MINIMAL_TEACHING_PLAN)
        assert "A &amp; B conditions" in html

    def test_html_in_discussion_prompt_escaped(self):
        content = {**_MINIMAL_CONTENT, "discussion_prompts": ['What if <b>this</b> happens?']}
        html = _fill_template(content, _MINIMAL_STATE, _MINIMAL_SVGS, _MINIMAL_TEACHING_PLAN)
        assert "<b>" not in html
        assert "&lt;b&gt;" in html

    def test_esc_function_directly(self):
        assert _esc("<") == "&lt;"
        assert _esc(">") == "&gt;"
        assert _esc("&") == "&amp;"
        assert _esc('"') == "&quot;"
        assert _esc("safe text") == "safe text"


class TestRenderReelScenes:
    def test_six_scenes_produce_six_divs(self):
        scenes = _MINIMAL_CONTENT["reel_scenes"]
        html = _render_reel_scenes(scenes)
        count = html.count('class="reel-scene"')
        assert count == 6

    def test_scene_timestamp_appears(self):
        scenes = [{"timestamp": "0:00-0:05", "title": "Hook", "visual": "[v]", "script": "Text."}]
        html = _render_reel_scenes(scenes)
        assert "0:00-0:05" in html

    def test_scene_title_in_scene_title_div(self):
        scenes = [{"timestamp": "0:00-0:05", "title": "Hook", "visual": "[v]", "script": "Text."}]
        html = _render_reel_scenes(scenes)
        assert 'class="scene-title"' in html
        assert "Hook" in html

    def test_scene_visual_in_scene_visual_div(self):
        scenes = [{"timestamp": "0:00-0:05", "title": "Hook", "visual": "[show diagram]", "script": "Text."}]
        html = _render_reel_scenes(scenes)
        assert 'class="scene-visual"' in html
        assert "[show diagram]" in html

    def test_empty_scenes_returns_empty_string(self):
        html = _render_reel_scenes([])
        assert html == ""

    def test_special_chars_in_scene_escaped(self):
        scenes = [{"timestamp": "0:00-0:05", "title": "<Injection>", "visual": "[v]", "script": "Text."}]
        html = _render_reel_scenes(scenes)
        assert "<Injection>" not in html
        assert "&lt;Injection&gt;" in html


class TestRenderDiagram:
    def test_valid_spec_produces_svg(self):
        spec = {
            "diagram_type": "state_machine",
            "title": "CB States",
            "placement": "main",
            "nodes": [
                {"id": "closed", "label": "CLOSED", "x": 40, "y": 110, "w": 160, "h": 60, "color": "green"},
                {"id": "open", "label": "OPEN", "x": 480, "y": 110, "w": 160, "h": 60, "color": "red"},
            ],
            "edges": [{"from_id": "closed", "to_id": "open", "label": "fail"}],
        }
        svg = _render_diagram(spec)
        assert "<svg" in svg
        assert "CLOSED" in svg
        assert "OPEN" in svg

    def test_empty_nodes_returns_fallback_svg(self):
        spec = {"diagram_type": "state_machine", "title": "Empty", "placement": "main", "nodes": [], "edges": []}
        svg = _render_diagram(spec)
        assert "<svg" in svg

    def test_missing_nodes_key_returns_fallback(self):
        spec = {"diagram_type": "state_machine", "title": "Bad"}
        svg = _render_diagram(spec)
        assert "<svg" in svg

    def test_edges_with_dashed_true_render(self):
        spec = {
            "diagram_type": "state_machine",
            "title": "Recovery",
            "placement": "main",
            "nodes": [
                {"id": "a", "label": "A", "x": 40, "y": 110, "w": 160, "h": 60, "color": "blue"},
                {"id": "b", "label": "B", "x": 280, "y": 110, "w": 160, "h": 60, "color": "blue"},
            ],
            "edges": [{"from_id": "a", "to_id": "b", "label": "timeout", "dashed": True}],
        }
        svg = _render_diagram(spec)
        assert "stroke-dasharray" in svg


class TestFallbackSVG:
    def test_produces_valid_svg(self):
        svg = _fallback_svg("My Diagram")
        assert "<svg" in svg
        assert "viewBox" in svg
        assert "</svg>" in svg

    def test_title_appears_in_svg(self):
        svg = _fallback_svg("Problem Scenario")
        assert "Problem Scenario" in svg

    def test_empty_title_does_not_crash(self):
        svg = _fallback_svg("")
        assert "<svg" in svg
