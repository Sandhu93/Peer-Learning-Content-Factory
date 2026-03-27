"""
File reader tools: extract functions, classes, and doc files from the repo.
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def read_file(
    file_path: str | Path,
    repo_path: Path | None = None,
    max_lines: int = 500,
) -> str:
    """Read an entire file from the repo (or an absolute path)."""
    full = _resolve(file_path, repo_path)
    if not full.exists():
        raise FileNotFoundError(f"Not found: {full}")
    lines = full.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[:max_lines])


def extract_function(
    file_path: str | Path,
    function_name: str,
    repo_path: Path | None = None,
) -> str | None:
    """
    Extract the source of a specific function from a Python file.
    Returns None if not found.
    """
    full = _resolve(file_path, repo_path)
    if not full.exists() or full.suffix != ".py":
        return None

    source = full.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == function_name:
                start = node.lineno - 1
                end = node.end_lineno or start + 1
                return "\n".join(lines[start:end])

    return None


def extract_class(
    file_path: str | Path,
    class_name: str,
    repo_path: Path | None = None,
) -> str | None:
    """Extract the source of a specific class from a Python file."""
    full = _resolve(file_path, repo_path)
    if not full.exists() or full.suffix != ".py":
        return None

    source = full.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            start = node.lineno - 1
            end = node.end_lineno or start + 1
            return "\n".join(lines[start:end])

    return None


def find_doc_files(repo_path: Path | None = None) -> list[Path]:
    """
    Return paths to documentation-like files in the repo:
    README.md, docs/, bugs.md, architecture.md, CHANGELOG.md, etc.
    """
    root = _resolve_repo(repo_path)
    patterns = [
        "README*.md",
        "readme*.md",
        "docs/**/*.md",
        "doc/**/*.md",
        "CHANGELOG*.md",
        "bugs*.md",
        "architecture*.md",
        "ARCHITECTURE*.md",
        "ADR*.md",
        "adr/**/*.md",
    ]
    found: list[Path] = []
    for pat in patterns:
        found.extend(root.glob(pat))

    # Deduplicate preserving order
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in found:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    return unique


def read_doc_file(path: Path, max_chars: int = 8000) -> str:
    """Read a doc file, truncating at max_chars if needed."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n... [truncated at {max_chars} chars]"
    return text


# ── Helpers ───────────────────────────────────────────────────────────────────


def _resolve(file_path: str | Path, repo_path: Path | None) -> Path:
    p = Path(file_path)
    if p.is_absolute():
        return p
    return _resolve_repo(repo_path) / p


def _resolve_repo(repo_path: Path | None) -> Path:
    if repo_path is not None:
        return repo_path
    from src.config import settings
    return settings.repo_path
