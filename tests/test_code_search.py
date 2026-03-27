"""
Unit tests for src/tools/code_search.py

These tests use the sample_repo fixture directory so they don't require
a real repo or API calls.
"""

import shutil
from pathlib import Path

import pytest

from src.tools.code_search import (
    find_tests,
    list_files,
    read_file_range,
    search_term,
    _to_camel,
    _to_snake,
)

# Mark classes that call ripgrep so they skip cleanly when rg is not installed
needs_rg = pytest.mark.skipif(
    not shutil.which("rg"),
    reason="ripgrep (rg) not installed — install from https://github.com/BurntSushi/ripgrep",
)

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "sample_repo"


@needs_rg
class TestSearchTerm:
    def test_finds_class_name(self):
        results = search_term("CircuitBreaker", repo_path=FIXTURE_REPO)
        assert len(results) > 0
        assert any("circuit_breaker" in r["file"] for r in results)

    def test_returns_line_number(self):
        results = search_term("CircuitBreaker", repo_path=FIXTURE_REPO)
        for r in results:
            assert isinstance(r["line_number"], int)
            assert r["line_number"] > 0

    def test_returns_line_text(self):
        results = search_term("CircuitBreaker", repo_path=FIXTURE_REPO)
        for r in results:
            assert "line_text" in r
            assert isinstance(r["line_text"], str)

    def test_no_results_for_unknown_term(self):
        results = search_term("xyzzy_nonexistent_term_abc", repo_path=FIXTURE_REPO)
        assert results == []

    def test_finds_enum_state(self):
        results = search_term("CLOSED", repo_path=FIXTURE_REPO)
        assert len(results) > 0


@needs_rg
class TestFindTests:
    def test_finds_test_file(self):
        results = find_tests("circuit breaker", repo_path=FIXTURE_REPO)
        # The fixture has test_circuit_breaker.py
        assert len(results) > 0

    def test_empty_for_missing_concept(self):
        results = find_tests("nonexistent concept xyz", repo_path=FIXTURE_REPO)
        assert results == []


class TestReadFileRange:
    def test_reads_full_file(self):
        content = read_file_range(
            "circuit_breaker.py",
            repo_path=FIXTURE_REPO,
        )
        assert "CircuitBreaker" in content
        assert "State" in content

    def test_reads_line_range(self):
        content = read_file_range(
            "circuit_breaker.py",
            start_line=1,
            end_line=5,
            repo_path=FIXTURE_REPO,
        )
        lines = content.splitlines()
        assert len(lines) <= 5

    def test_raises_for_missing_file(self):
        with pytest.raises(FileNotFoundError):
            read_file_range("nonexistent_file.py", repo_path=FIXTURE_REPO)


class TestListFiles:
    def test_lists_python_files(self):
        files = list_files(repo_path=FIXTURE_REPO, file_glob="*.py")
        assert len(files) > 0
        assert all(f.endswith(".py") for f in files)

    def test_empty_for_bad_glob(self):
        files = list_files(repo_path=FIXTURE_REPO, file_glob="*.xyz_never_exists")
        assert files == []


class TestHelpers:
    def test_to_snake(self):
        assert _to_snake("Circuit Breaker") == "circuit_breaker"
        assert _to_snake("retry with exponential backoff") == "retry_with_exponential_backoff"

    def test_to_camel(self):
        assert _to_camel("circuit breaker") == "CircuitBreaker"
        assert _to_camel("retry") == "Retry"
