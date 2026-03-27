"""
Parse peer_learning_concepts.md into a structured list of concept records.

Expected format per concept block:
    ### <Concept Name>
    - **Concept**: <name>
    - **Category**: <category>
    - **Why it matters**: <rationale>
    - **Repo anchors**: <comma or space separated search terms>

Usage:
    from src.utils.markdown_parser import parse_concepts, ConceptRecord

    concepts = parse_concepts()          # reads from settings.concepts_file
    concepts = parse_concepts(path)      # explicit path
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ConceptRecord:
    concept_name: str
    category: str
    why_it_matters: str
    repo_anchors: list[str]
    raw_heading: str = ""  # the ### heading text (may differ slightly from concept_name)

    def slug(self) -> str:
        """URL-safe slug derived from concept_name."""
        s = self.concept_name.lower()
        s = re.sub(r"[^a-z0-9]+", "-", s)
        return s.strip("-")


# Regex patterns for bullet fields
_FIELD_RE = re.compile(
    r"-\s+\*\*(?P<key>[^*]+)\*\*:\s*(?P<value>.+)",
    re.IGNORECASE,
)
_HEADING_RE = re.compile(r"^###\s+(.+)$", re.MULTILINE)


def parse_concepts(path: Path | None = None) -> list[ConceptRecord]:
    """
    Parse the concept backlog markdown file and return all ConceptRecord objects.

    Concepts are identified by ### headings followed by bullet-list fields.
    Category-level ## headings are tracked as context but the concept's own
    **Category** field takes precedence if present.
    """
    if path is None:
        from src.config import settings
        path = settings.concepts_file

    text = Path(path).read_text(encoding="utf-8")
    return _parse_text(text)


def _parse_text(text: str) -> list[ConceptRecord]:
    records: list[ConceptRecord] = []
    current_category: str = ""

    # Split into blocks; process line by line for context
    lines = text.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i].rstrip()

        # Track ## category headings for fallback
        if line.startswith("## ") and not line.startswith("### "):
            # Strip leading "## Category: " prefix if present
            heading = line[3:].strip()
            if heading.lower().startswith("category:"):
                heading = heading[len("category:"):].strip()
            current_category = heading
            i += 1
            continue

        # Concept block starts at ### heading
        if line.startswith("### "):
            heading_text = line[4:].strip()
            fields: dict[str, str] = {}

            # Collect bullet fields until the next heading or blank line sequence
            i += 1
            while i < len(lines):
                l = lines[i].rstrip()
                if l.startswith("#"):
                    break  # next heading — stop collecting
                m = _FIELD_RE.match(l)
                if m:
                    fields[m.group("key").strip().lower()] = m.group("value").strip()
                i += 1

            if not fields:
                continue  # heading with no fields — skip

            concept_name = fields.get("concept", heading_text)
            category = fields.get("category", current_category)
            why = fields.get("why it matters", "")
            anchors_raw = fields.get("repo anchors", "")
            anchors = [a.strip() for a in re.split(r"[,\s]+", anchors_raw) if a.strip()]

            records.append(
                ConceptRecord(
                    concept_name=concept_name,
                    category=category,
                    why_it_matters=why,
                    repo_anchors=anchors,
                    raw_heading=heading_text,
                )
            )
            continue

        i += 1

    return records


def find_concept(name: str, path: Path | None = None) -> ConceptRecord | None:
    """
    Case-insensitive fuzzy match for a concept by name.
    Returns the best match or None.
    """
    concepts = parse_concepts(path)
    name_lower = name.lower()

    # Exact match first
    for c in concepts:
        if c.concept_name.lower() == name_lower:
            return c

    # Substring match
    for c in concepts:
        if name_lower in c.concept_name.lower() or c.concept_name.lower() in name_lower:
            return c

    return None


def list_categories(path: Path | None = None) -> list[str]:
    """Return all unique categories in the backlog, preserving order."""
    seen: list[str] = []
    for c in parse_concepts(path):
        if c.category not in seen:
            seen.append(c.category)
    return seen
