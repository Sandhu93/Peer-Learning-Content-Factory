"""
Ripgrep-based codebase search tools.

All functions take an optional `repo_path` argument; when omitted they use
`settings.repo_path`. This makes them easy to test with fixture directories.

Requires `rg` (ripgrep) to be installed and on PATH.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# File extensions we consider source code (skip binaries, lock files, etc.)
_SOURCE_GLOB = (
    "*.py,*.ts,*.tsx,*.js,*.jsx,*.go,*.rs,*.java,*.rb,*.swift,"
    "*.c,*.cpp,*.h,*.cs,*.md,*.yaml,*.yml,*.toml,*.json,*.sql"
)


def _glob_args(glob_str: str) -> list[str]:
    """
    Convert a comma-separated glob string into a flat list of --glob flags.

    ripgrep requires one --glob flag per pattern:
        _glob_args("*.py,*.ts") → ["--glob", "*.py", "--glob", "*.ts"]
    """
    args: list[str] = []
    for pat in glob_str.split(","):
        pat = pat.strip()
        if pat:
            args.extend(["--glob", pat])
    return args

# Maximum number of matches returned per search to avoid overwhelming context
_MAX_MATCHES = 30


def _rg(*args: str) -> list[dict]:
    """
    Run ripgrep with JSON output and return parsed match objects.
    Each dict is a ripgrep JSON line of type "match".
    """
    cmd = ["rg", "--json", *args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        raise RuntimeError(
            "ripgrep (rg) not found on PATH. Install it: https://github.com/BurntSushi/ripgrep"
        )
    except subprocess.TimeoutExpired:
        logger.warning("ripgrep timed out for: %s", " ".join(args))
        return []

    matches = []
    for line in result.stdout.splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "match":
            matches.append(obj)

    return matches[:_MAX_MATCHES]


def search_term(
    term: str,
    repo_path: Path | None = None,
    case_insensitive: bool = False,
    file_glob: str | None = None,
) -> list[dict]:
    """
    Search for a term in the codebase.

    Returns a list of match records:
    {
        "file": str,
        "line_number": int,
        "line_text": str,
        "context_before": list[str],
        "context_after": list[str],
    }
    """
    repo = _resolve_repo(repo_path)
    args = ["--context", "3", *_glob_args(file_glob or _SOURCE_GLOB)]
    if case_insensitive:
        args.append("--ignore-case")
    args += [term, str(repo)]

    raw_matches = _rg(*args)
    return [_format_match(m) for m in raw_matches]


def search_pattern(
    pattern: str,
    repo_path: Path | None = None,
    file_glob: str | None = None,
) -> list[dict]:
    """
    Search using a regex pattern. Same return format as search_term.
    """
    repo = _resolve_repo(repo_path)
    args = [
        "--context", "3",
        *_glob_args(file_glob or _SOURCE_GLOB),
        pattern,
        str(repo),
    ]
    raw_matches = _rg(*args)
    return [_format_match(m) for m in raw_matches]


def find_tests(
    concept_name: str,
    repo_path: Path | None = None,
) -> list[dict]:
    """
    Search for test files related to a concept name.

    Looks for the concept name (snake_case and CamelCase variants) inside
    files that match test_*.py / *_test.py / *.test.ts patterns.
    """
    repo = _resolve_repo(repo_path)
    slug = _to_snake(concept_name)

    # Try both snake_case and camelCase
    patterns = [slug, _to_camel(concept_name)]
    results: list[dict] = []

    for pat in patterns:
        raw = _rg(
            *_glob_args("test_*.py,*_test.py,*.test.ts,*.test.js,*.spec.ts,*.spec.js"),
            "--context", "2",
            pat,
            str(repo),
        )
        results.extend(_format_match(m) for m in raw)
        if results:
            break

    return results[:_MAX_MATCHES]


def read_file_range(
    file_path: str | Path,
    start_line: int = 1,
    end_line: int | None = None,
    repo_path: Path | None = None,
) -> str:
    """
    Read a specific line range from a file in the repo.

    file_path may be absolute or relative to repo_path.
    Returns the file content as a string.
    """
    repo = _resolve_repo(repo_path)
    full_path = Path(file_path) if Path(file_path).is_absolute() else repo / file_path

    if not full_path.exists():
        raise FileNotFoundError(f"File not found: {full_path}")

    lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(0, start_line - 1)
    end = end_line if end_line else len(lines)
    return "\n".join(lines[start:end])


def list_files(
    repo_path: Path | None = None,
    file_glob: str = "*.py",
    max_files: int = 200,
) -> list[str]:
    """
    List files matching a glob pattern, relative to repo_path.
    Uses ripgrep when available; falls back to Path.rglob otherwise.
    """
    repo = _resolve_repo(repo_path)

    # Try ripgrep first (faster on large repos)
    if _rg_available():
        cmd = ["rg", "--files", "--glob", file_glob, str(repo)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            files = [
                str(Path(p).relative_to(repo))
                for p in result.stdout.splitlines()
                if p.strip()
            ]
            return files[:max_files]
        except subprocess.TimeoutExpired:
            pass  # fall through to Python fallback

    # Pure-Python fallback — works without ripgrep installed
    _SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules"}
    found: list[str] = []
    for pat in file_glob.split(","):
        pat = pat.strip()
        for p in repo.rglob(pat):
            if any(s in p.parts for s in _SKIP_DIRS):
                continue
            if p.is_file():
                found.append(str(p.relative_to(repo)))
            if len(found) >= max_files:
                break
        if len(found) >= max_files:
            break

    return found[:max_files]


# ── Internal helpers ──────────────────────────────────────────────────────────


def _rg_available() -> bool:
    """Return True if ripgrep is installed and on PATH."""
    import shutil
    return shutil.which("rg") is not None


def _resolve_repo(repo_path: Path | None) -> Path:
    if repo_path is not None:
        return repo_path
    from src.config import settings
    return settings.repo_path


def _format_match(raw: dict) -> dict:
    data = raw.get("data", {})
    path = data.get("path", {}).get("text", "")
    line_number = data.get("line_number", 0)
    line_text = data.get("lines", {}).get("text", "").rstrip("\n")
    submatches = data.get("submatches", [])

    return {
        "file": path,
        "line_number": line_number,
        "line_text": line_text,
        "match": submatches[0].get("match", {}).get("text", "") if submatches else "",
    }


def _to_snake(s: str) -> str:
    """'Circuit Breaker' → 'circuit_breaker'"""
    import re
    s = re.sub(r"[^a-zA-Z0-9]", "_", s.lower())
    return re.sub(r"_+", "_", s).strip("_")


def _to_camel(s: str) -> str:
    """'circuit breaker' → 'CircuitBreaker'"""
    return "".join(w.capitalize() for w in s.split())
