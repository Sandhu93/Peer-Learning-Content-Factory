"""
Unit tests for src/utils/markdown_parser.py
"""

from pathlib import Path

import pytest

from src.utils.markdown_parser import (
    ConceptRecord,
    find_concept,
    list_categories,
    parse_concepts,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_concepts.md"


class TestParseConcepts:
    def test_returns_list(self):
        concepts = parse_concepts(FIXTURE)
        assert isinstance(concepts, list)
        assert len(concepts) == 3

    def test_first_concept_name(self):
        concepts = parse_concepts(FIXTURE)
        assert concepts[0].concept_name == "Circuit breaker for provider failure"

    def test_category_parsed(self):
        concepts = parse_concepts(FIXTURE)
        assert "Reliability" in concepts[0].category

    def test_why_it_matters_populated(self):
        concepts = parse_concepts(FIXTURE)
        assert "cascading failures" in concepts[0].why_it_matters

    def test_repo_anchors_split(self):
        concepts = parse_concepts(FIXTURE)
        anchors = concepts[0].repo_anchors
        assert isinstance(anchors, list)
        assert "circuit_breaker" in anchors
        assert "CircuitBreaker" in anchors

    def test_second_category(self):
        concepts = parse_concepts(FIXTURE)
        assert concepts[2].category == "Observability and Debugging"

    def test_all_records_are_concept_records(self):
        concepts = parse_concepts(FIXTURE)
        for c in concepts:
            assert isinstance(c, ConceptRecord)


class TestSlug:
    def test_basic_slug(self):
        c = ConceptRecord(
            concept_name="Circuit breaker for provider failure",
            category="",
            why_it_matters="",
            repo_anchors=[],
        )
        assert c.slug() == "circuit-breaker-for-provider-failure"

    def test_slug_with_parens(self):
        c = ConceptRecord(
            concept_name="Pagination strategies (cursor vs offset)",
            category="",
            why_it_matters="",
            repo_anchors=[],
        )
        slug = c.slug()
        assert " " not in slug
        assert "(" not in slug


class TestFindConcept:
    def test_exact_match(self):
        result = find_concept("Circuit breaker for provider failure", FIXTURE)
        assert result is not None
        assert result.concept_name == "Circuit breaker for provider failure"

    def test_case_insensitive(self):
        result = find_concept("circuit breaker for provider failure", FIXTURE)
        assert result is not None

    def test_partial_match(self):
        result = find_concept("exponential backoff", FIXTURE)
        assert result is not None
        assert "Retry" in result.concept_name

    def test_not_found(self):
        result = find_concept("nonexistent concept xyz", FIXTURE)
        assert result is None


class TestListCategories:
    def test_returns_unique_ordered(self):
        cats = list_categories(FIXTURE)
        assert cats[0] == "Reliability, Failure Isolation, and Production Hardening"
        assert cats[1] == "Observability and Debugging"
        assert len(cats) == 2
