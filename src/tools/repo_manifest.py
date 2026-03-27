"""
Build a high-level manifest of the target repository for context injection.

The manifest gives agents a map of what's in the repo without reading every file.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def build_manifest(
    repo_path: Path | None = None,
    max_depth: int = 3,
    max_files: int = 300,
) -> str:
    """
    Return a text representation of the repo directory tree (directories only)
    plus a count of source files by extension.
    """
    root = _resolve_repo(repo_path)
    tree = _tree(root, max_depth=max_depth)
    stats = _file_stats(root, max_files=max_files)
    return f"# Repository: {root.name}\n\n## Directory Tree\n```\n{tree}\n```\n\n## File Stats\n{stats}"


def _tree(root: Path, max_depth: int = 3, prefix: str = "", depth: int = 0) -> str:
    if depth > max_depth:
        return ""

    _SKIP = {
        ".git", "__pycache__", ".venv", "venv", "node_modules",
        ".mypy_cache", ".ruff_cache", ".pytest_cache", "dist", "build",
    }

    lines: list[str] = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return ""

    dirs = [e for e in entries if e.is_dir() and e.name not in _SKIP]
    files = [e for e in entries if e.is_file()]

    for i, d in enumerate(dirs):
        is_last = i == len(dirs) - 1 and not files
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{d.name}/")
        extension = "    " if is_last else "│   "
        subtree = _tree(d, max_depth, prefix + extension, depth + 1)
        if subtree:
            lines.append(subtree)

    for i, f in enumerate(files[:20]):  # show max 20 files per dir
        connector = "└── " if i == len(files) - 1 else "├── "
        lines.append(f"{prefix}{connector}{f.name}")

    if len(files) > 20:
        lines.append(f"{prefix}└── ... ({len(files) - 20} more files)")

    return "\n".join(lines)


def _file_stats(root: Path, max_files: int = 300) -> str:
    ext_counts: dict[str, int] = {}
    count = 0
    _SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules"}

    for path in root.rglob("*"):
        if count >= max_files:
            break
        if any(s in path.parts for s in _SKIP_DIRS):
            continue
        if path.is_file():
            ext = path.suffix.lower() or "(no ext)"
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
            count += 1

    lines = []
    for ext, n in sorted(ext_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {ext:<12} {n:>4} files")
    return "\n".join(lines) if lines else "  (empty)"


def _resolve_repo(repo_path: Path | None) -> Path:
    if repo_path is not None:
        return repo_path
    from src.config import settings
    return settings.repo_path
