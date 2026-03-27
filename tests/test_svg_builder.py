"""
Unit tests for src/utils/svg_builder.py

Tests focus on:
  - SVG structure (valid output)
  - CSS custom property color references (dark mode compatibility)
  - Text escaping for HTML-special characters in labels
  - Edge cases: empty inputs, single nodes, missing optional fields
"""

from __future__ import annotations

import pytest

from src.utils.svg_builder import SVGCanvas, _esc, create_state_machine


class TestSVGCanvas:
    def test_render_produces_svg_element(self):
        svg = SVGCanvas().render()
        assert svg.startswith("<svg")
        assert "</svg>" in svg

    def test_render_includes_viewbox(self):
        svg = SVGCanvas(680, 320).render()
        assert 'viewBox="0 0 680 320"' in svg

    def test_render_includes_width_in_style(self):
        svg = SVGCanvas(680, 320).render()
        assert "width:100%" in svg
        assert "max-width:680px" in svg

    def test_empty_canvas_renders_cleanly(self):
        svg = SVGCanvas().render()
        # No element content but still valid SVG wrapper
        assert "<svg" in svg
        assert "</svg>" in svg

    def test_add_rect_uses_css_var_for_color(self):
        canvas = SVGCanvas()
        canvas.add_rect(10, 10, 100, 50, label="NODE", color="green")
        svg = canvas.render()
        assert "var(--color-success)" in svg

    def test_add_rect_red_uses_error_var(self):
        canvas = SVGCanvas()
        canvas.add_rect(10, 10, 100, 50, label="OPEN", color="red")
        svg = canvas.render()
        assert "var(--color-error)" in svg

    def test_add_rect_amber_uses_warning_var(self):
        canvas = SVGCanvas()
        canvas.add_rect(10, 10, 100, 50, label="HALF", color="amber")
        svg = canvas.render()
        assert "var(--color-warning)" in svg

    def test_add_rect_label_appears_in_text_element(self):
        canvas = SVGCanvas()
        canvas.add_rect(10, 10, 100, 50, label="CLOSED")
        svg = canvas.render()
        assert "CLOSED" in svg

    def test_add_rect_subtitle_appears_when_provided(self):
        canvas = SVGCanvas()
        canvas.add_rect(10, 10, 100, 50, label="CLOSED", subtitle="normal")
        svg = canvas.render()
        assert "normal" in svg

    def test_add_circle_produces_circle_element(self):
        canvas = SVGCanvas()
        canvas.add_circle(100, 100, 40, label="START", color="blue")
        svg = canvas.render()
        assert "<circle" in svg
        assert "START" in svg

    def test_add_arrow_produces_line_element(self):
        canvas = SVGCanvas()
        canvas.add_arrow(50, 50, 200, 50)
        svg = canvas.render()
        assert "<line" in svg

    def test_add_arrow_with_label_includes_text(self):
        canvas = SVGCanvas()
        canvas.add_arrow(50, 50, 200, 50, label="transition")
        svg = canvas.render()
        assert "transition" in svg

    def test_add_arrow_dashed_includes_stroke_dasharray(self):
        canvas = SVGCanvas()
        canvas.add_arrow(50, 50, 200, 50, dashed=True)
        svg = canvas.render()
        assert "stroke-dasharray" in svg

    def test_add_arrow_solid_no_dasharray(self):
        canvas = SVGCanvas()
        canvas.add_arrow(50, 50, 200, 50, dashed=False)
        svg = canvas.render()
        assert "stroke-dasharray" not in svg

    def test_add_text_appears_in_output(self):
        canvas = SVGCanvas()
        canvas.add_text(100, 50, "Hello World")
        svg = canvas.render()
        assert "Hello World" in svg

    def test_add_text_bold_sets_font_weight_700(self):
        canvas = SVGCanvas()
        canvas.add_text(100, 50, "Bold", bold=True)
        svg = canvas.render()
        assert 'font-weight="700"' in svg

    def test_method_chaining_returns_canvas(self):
        canvas = SVGCanvas()
        result = canvas.add_rect(10, 10, 100, 50, label="A")
        assert result is canvas

    def test_unknown_color_falls_back_to_literal(self):
        """If a color name isn't in COLOR_MAP, use the literal value."""
        canvas = SVGCanvas()
        canvas.add_rect(10, 10, 100, 50, label="X", color="#ff0000")
        svg = canvas.render()
        assert "#ff0000" in svg


class TestTextEscaping:
    def test_escapes_less_than(self):
        assert _esc("<script>") == "&lt;script&gt;"

    def test_escapes_greater_than(self):
        assert _esc("a > b") == "a &gt; b"

    def test_escapes_ampersand(self):
        assert _esc("A&B") == "A&amp;B"

    def test_escapes_double_quote(self):
        assert _esc('say "hello"') == "say &quot;hello&quot;"

    def test_safe_string_unchanged(self):
        assert _esc("Circuit Breaker") == "Circuit Breaker"

    def test_empty_string_unchanged(self):
        assert _esc("") == ""

    def test_xss_attempt_in_node_label_is_escaped(self):
        canvas = SVGCanvas()
        canvas.add_rect(10, 10, 100, 50, label='<script>alert(1)</script>')
        svg = canvas.render()
        assert "<script>" not in svg
        assert "&lt;script&gt;" in svg


class TestCreateStateMachine:
    def test_basic_three_state_machine(self):
        states = [
            {"id": "closed", "label": "CLOSED", "x": 40, "y": 110, "w": 160, "h": 60, "color": "green"},
            {"id": "open", "label": "OPEN", "x": 480, "y": 110, "w": 160, "h": 60, "color": "red"},
            {"id": "half", "label": "HALF-OPEN", "x": 260, "y": 110, "w": 160, "h": 60, "color": "amber"},
        ]
        transitions = [
            {"from_id": "closed", "to_id": "open", "label": "failures > threshold"},
            {"from_id": "open", "to_id": "half", "label": "timeout elapsed", "dashed": True},
            {"from_id": "half", "to_id": "closed", "label": "success"},
        ]
        svg = create_state_machine(states, transitions)

        assert "<svg" in svg
        assert "CLOSED" in svg
        assert "OPEN" in svg
        assert "HALF-OPEN" in svg
        assert "<line" in svg  # at least one transition arrow

    def test_empty_states_returns_svg(self):
        """No nodes — should still return a valid SVG, not raise."""
        svg = create_state_machine([], [])
        assert "<svg" in svg

    def test_transitions_with_unknown_ids_are_skipped(self):
        """If from_id or to_id doesn't match a node, skip the transition gracefully."""
        states = [
            {"id": "a", "label": "A", "x": 40, "y": 110, "w": 160, "h": 60, "color": "blue"},
        ]
        transitions = [
            {"from_id": "a", "to_id": "nonexistent", "label": "bad edge"},
        ]
        # Should not raise KeyError
        svg = create_state_machine(states, transitions)
        assert "A" in svg

    def test_single_node_no_transitions(self):
        states = [{"id": "only", "label": "ONLY", "x": 260, "y": 110, "w": 160, "h": 60, "color": "purple"}]
        svg = create_state_machine(states, [])
        assert "ONLY" in svg
        assert "<line" not in svg

    def test_state_colors_use_css_vars(self):
        states = [
            {"id": "g", "label": "OK", "x": 40, "y": 110, "w": 160, "h": 60, "color": "green"},
            {"id": "r", "label": "FAIL", "x": 280, "y": 110, "w": 160, "h": 60, "color": "red"},
        ]
        svg = create_state_machine(states, [])
        assert "var(--color-success)" in svg
        assert "var(--color-error)" in svg

    def test_dashed_transition_produces_stroke_dasharray(self):
        states = [
            {"id": "a", "label": "A", "x": 40, "y": 110, "w": 160, "h": 60, "color": "blue"},
            {"id": "b", "label": "B", "x": 280, "y": 110, "w": 160, "h": 60, "color": "blue"},
        ]
        transitions = [{"from_id": "a", "to_id": "b", "label": "probe", "dashed": True}]
        svg = create_state_machine(states, transitions)
        assert "stroke-dasharray" in svg

    def test_node_default_dimensions_used_when_absent(self):
        """w and h default to 160×60 when not in spec."""
        states = [{"id": "x", "label": "X", "x": 40, "y": 110, "color": "gray"}]
        # No KeyError for missing w/h
        svg = create_state_machine(states, [])
        assert "X" in svg

    def test_custom_canvas_dimensions(self):
        svg = create_state_machine([], [], width=400, height=200)
        assert 'viewBox="0 0 400 200"' in svg
