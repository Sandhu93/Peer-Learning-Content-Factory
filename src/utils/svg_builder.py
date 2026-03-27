"""
Programmatic SVG construction helpers matching the guide design system.

Color system (CSS custom properties — works in both light and dark mode):
    green  → var(--color-success)   — closed/healthy/passing states
    red    → var(--color-error)     — open/failed/broken states
    amber  → var(--color-warning)   — half-open/degraded states
    blue   → var(--color-blue)      — service/component nodes
    coral  → var(--color-coral)     — infrastructure nodes
    purple → var(--color-purple)    — abstract concept nodes
    gray   → var(--color-gray)      — neutral/inactive nodes

Usage:
    from src.utils.svg_builder import SVGCanvas, create_state_machine

    canvas = SVGCanvas(680, 320)
    canvas.add_rect(40, 40, 160, 60, label="CLOSED", color="green")
    canvas.add_arrow(200, 70, 300, 70, label="fail")
    print(canvas.render())
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field

# Mapping of semantic color names → CSS variables defined in guide_template.html
COLOR_MAP = {
    "green": "var(--color-success)",
    "red": "var(--color-error)",
    "amber": "var(--color-warning)",
    "blue": "var(--color-blue)",
    "coral": "var(--color-coral)",
    "purple": "var(--color-purple)",
    "gray": "var(--color-gray)",
}


def _color(name: str) -> str:
    return COLOR_MAP.get(name, name)  # fall back to literal value if not in map


@dataclass
class SVGElement:
    markup: str


@dataclass
class SVGCanvas:
    width: int = 680
    height: int = 320
    _elements: list[SVGElement] = field(default_factory=list)

    def add_rect(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        label: str,
        subtitle: str = "",
        color: str = "blue",
        rx: int = 8,
    ) -> "SVGCanvas":
        fill = _color(color)
        label_escaped = _esc(label)
        cy = y + h // 2 + (0 if not subtitle else -8)
        parts = [
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"'
            f' fill="{fill}" fill-opacity="0.15" stroke="{fill}" stroke-width="1.5"/>',
            f'<text x="{x + w//2}" y="{cy}" text-anchor="middle"'
            f' dominant-baseline="middle" font-family="var(--font)" font-size="14"'
            f' font-weight="600" fill="{fill}">{label_escaped}</text>',
        ]
        if subtitle:
            parts.append(
                f'<text x="{x + w//2}" y="{y + h//2 + 12}" text-anchor="middle"'
                f' dominant-baseline="middle" font-family="var(--font)" font-size="11"'
                f' fill="{fill}" opacity="0.75">{_esc(subtitle)}</text>'
            )
        self._elements.append(SVGElement("\n".join(parts)))
        return self

    def add_circle(
        self,
        cx: int,
        cy: int,
        r: int,
        label: str,
        color: str = "blue",
    ) -> "SVGCanvas":
        fill = _color(color)
        self._elements.append(
            SVGElement(
                f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" fill-opacity="0.15"'
                f' stroke="{fill}" stroke-width="1.5"/>\n'
                f'<text x="{cx}" y="{cy}" text-anchor="middle" dominant-baseline="middle"'
                f' font-family="var(--font)" font-size="13" font-weight="600"'
                f' fill="{fill}">{_esc(label)}</text>'
            )
        )
        return self

    def add_arrow(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        label: str = "",
        color: str = "var(--text-muted)",
        dashed: bool = False,
    ) -> "SVGCanvas":
        dash = 'stroke-dasharray="6 3"' if dashed else ""
        mid_x = (x1 + x2) // 2
        mid_y = (y1 + y2) // 2 - 8
        parts = [
            f'<defs><marker id="arr_{id(self)}_{len(self._elements)}" markerWidth="8"'
            f' markerHeight="8" refX="6" refY="3" orient="auto">'
            f'<path d="M0,0 L0,6 L8,3 z" fill="{color}"/></marker></defs>',
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}"'
            f' stroke-width="1.5" {dash}'
            f' marker-end="url(#arr_{id(self)}_{len(self._elements) - 1})"/>',
        ]
        if label:
            parts.append(
                f'<text x="{mid_x}" y="{mid_y}" text-anchor="middle"'
                f' font-family="var(--font)" font-size="11" fill="{color}"'
                f' opacity="0.85">{_esc(label)}</text>'
            )
        self._elements.append(SVGElement("\n".join(parts)))
        return self

    def add_text(
        self,
        x: int,
        y: int,
        text: str,
        size: int = 12,
        anchor: str = "middle",
        bold: bool = False,
        color: str = "var(--text)",
    ) -> "SVGCanvas":
        weight = "700" if bold else "400"
        self._elements.append(
            SVGElement(
                f'<text x="{x}" y="{y}" text-anchor="{anchor}"'
                f' font-family="var(--font)" font-size="{size}" font-weight="{weight}"'
                f' fill="{color}">{_esc(text)}</text>'
            )
        )
        return self

    def render(self) -> str:
        body = "\n  ".join(e.markup for e in self._elements)
        return textwrap.dedent(f"""\
            <svg viewBox="0 0 {self.width} {self.height}"
                 xmlns="http://www.w3.org/2000/svg"
                 style="width:100%;max-width:{self.width}px;height:auto">
              {body}
            </svg>""")


# ── Convenience constructors ──────────────────────────────────────────────────


def create_state_machine(
    states: list[dict],
    transitions: list[dict],
    width: int = 680,
    height: int = 280,
) -> str:
    """
    Build a state-machine SVG from a declarative spec.

    states: [{id, label, subtitle?, x, y, w?, h?, color}]
    transitions: [{from_id, to_id, label?, dashed?}]
    """
    canvas = SVGCanvas(width, height)
    node_centers: dict[str, tuple[int, int]] = {}

    for s in states:
        w = s.get("w", 160)
        h = s.get("h", 60)
        x, y = s["x"], s["y"]
        canvas.add_rect(x, y, w, h, s["label"], s.get("subtitle", ""), s.get("color", "blue"))
        node_centers[s["id"]] = (x + w // 2, y + h // 2)

    for t in transitions:
        src = node_centers.get(t["from_id"])
        dst = node_centers.get(t["to_id"])
        if src and dst:
            canvas.add_arrow(*src, *dst, t.get("label", ""), dashed=t.get("dashed", False))

    return canvas.render()


def _esc(s: str) -> str:
    """Escape XML special characters."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
