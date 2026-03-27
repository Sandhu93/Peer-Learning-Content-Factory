"""
Integration tests for the LangGraph pipeline graph.

These tests mock the LLM calls so they run without API keys.
The goal is to verify state transitions, not LLM quality.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.state import PipelineState

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "sample_repo"

# Sample LLM responses — valid JSON that the agents can parse
_TOPIC_PARSER_RESPONSE = """{
  "concept_name": "Circuit breaker for provider failure",
  "category": "Reliability, Failure Isolation, and Production Hardening",
  "why_it_matters": "Prevents cascading failures when an upstream LLM provider becomes slow or unavailable.",
  "difficulty": "intermediate",
  "prerequisites": ["retry with backoff", "timeout budgets"],
  "related_concepts": ["bulkhead pattern", "rate limiting"],
  "common_misconceptions": ["circuit breakers replace retries"],
  "key_terms": {"OPEN": "state where all requests fail fast", "HALF_OPEN": "recovery probe state"},
  "teaching_angles": ["the 3am outage that added this", "naive retry vs circuit breaker"],
  "repo_search_strategy": {
    "primary_terms": ["CircuitBreaker", "circuit_breaker"],
    "secondary_terms": ["OPEN", "HALF_OPEN", "failure_threshold"],
    "file_patterns": ["*.py"],
    "test_patterns": ["test_circuit"]
  }
}"""

_CODE_RESEARCHER_RESPONSE = """{
  "code_evidence": [
    {
      "file_path": "circuit_breaker.py",
      "line_start": 14,
      "line_end": 45,
      "content": "class CircuitBreaker: ...",
      "relevance": "Core implementation — shows state machine with CLOSED/OPEN/HALF_OPEN states"
    }
  ],
  "key_files": ["circuit_breaker.py"],
  "implementation_summary": "Uses a simple counter-based threshold with a recovery timeout.",
  "gaps": []
}"""


@pytest.fixture
def initial_state() -> PipelineState:
    return {
        "concept_name": "Circuit breaker for provider failure",
        "category": "Reliability, Failure Isolation, and Production Hardening",
        "why_it_matters": "Prevents cascading failures.",
        "repo_anchors": ["circuit_breaker", "CircuitBreaker"],
        "revision_count": 0,
        "is_complete": False,
        "errors": [],
    }


class TestGraphTopology:
    def test_graph_compiles(self):
        """Graph should build without errors."""
        from src.graph import build_graph
        graph = build_graph()
        assert graph is not None

    def test_graph_has_expected_nodes(self):
        from src.graph import build_graph
        graph = build_graph()
        # LangGraph compiled graphs expose node names
        node_names = set(graph.nodes.keys())
        assert "topic_parser" in node_names
        assert "code_researcher" in node_names


class TestTopicParserNode:
    @pytest.mark.asyncio
    async def test_enriches_concept(self, initial_state):
        from src.agents.topic_parser import topic_parser_node
        from src.utils.llm import LLMResponse

        mock_response = LLMResponse(
            content=_TOPIC_PARSER_RESPONSE,
            input_tokens=100,
            output_tokens=200,
            model="claude-sonnet-4-6",
            provider="anthropic",
        )

        with patch("src.agents.topic_parser.call_llm", new=AsyncMock(return_value=mock_response)):
            with patch("src.config.settings") as mock_settings:
                mock_settings.default_research_model = "claude-sonnet-4-6"
                result = await topic_parser_node(initial_state)

        assert result["concept_name"] == "Circuit breaker for provider failure"
        assert "teaching_plan" in result
        assert result["teaching_plan"]["difficulty"] == "intermediate"
        assert "CircuitBreaker" in result["teaching_plan"]["repo_search_strategy"]["primary_terms"]

    @pytest.mark.asyncio
    async def test_handles_malformed_json_gracefully(self, initial_state):
        from src.agents.topic_parser import topic_parser_node
        from src.utils.llm import LLMResponse

        mock_response = LLMResponse(
            content="This is not JSON at all",
            input_tokens=10,
            output_tokens=10,
            model="claude-sonnet-4-6",
            provider="anthropic",
        )

        with patch("src.agents.topic_parser.call_llm", new=AsyncMock(return_value=mock_response)):
            with patch("src.config.settings") as mock_settings:
                mock_settings.default_research_model = "claude-sonnet-4-6"
                result = await topic_parser_node(initial_state)

        # Should not crash — should fall back to defaults
        assert result["concept_name"] == initial_state["concept_name"]


class TestCodeResearcherNode:
    @pytest.mark.asyncio
    async def test_produces_code_evidence(self, initial_state):
        from src.agents.code_researcher import code_researcher_node
        from src.utils.llm import LLMResponse

        # First run topic_parser to populate teaching_plan
        state_with_plan = {
            **initial_state,
            "teaching_plan": {
                "repo_search_strategy": {
                    "primary_terms": ["CircuitBreaker"],
                    "secondary_terms": ["OPEN", "HALF_OPEN"],
                }
            },
        }

        mock_response = LLMResponse(
            content=_CODE_RESEARCHER_RESPONSE,
            input_tokens=500,
            output_tokens=300,
            model="claude-sonnet-4-6",
            provider="anthropic",
        )

        with patch("src.agents.code_researcher.call_llm", new=AsyncMock(return_value=mock_response)):
            with patch("src.config.settings") as mock_settings:
                mock_settings.default_research_model = "claude-sonnet-4-6"
                mock_settings.repo_path = FIXTURE_REPO
                result = await code_researcher_node(state_with_plan)

        assert "code_evidence" in result
        assert isinstance(result["code_evidence"], list)
        assert len(result["code_evidence"]) > 0

    @pytest.mark.asyncio
    async def test_populates_doc_context(self, initial_state):
        from src.agents.code_researcher import code_researcher_node
        from src.utils.llm import LLMResponse

        state_with_plan = {
            **initial_state,
            "teaching_plan": {
                "repo_search_strategy": {
                    "primary_terms": ["CircuitBreaker"],
                    "secondary_terms": [],
                }
            },
        }

        mock_response = LLMResponse(
            content=_CODE_RESEARCHER_RESPONSE,
            input_tokens=100,
            output_tokens=100,
            model="claude-sonnet-4-6",
            provider="anthropic",
        )

        with patch("src.agents.code_researcher.call_llm", new=AsyncMock(return_value=mock_response)):
            with patch("src.config.settings") as mock_settings:
                mock_settings.default_research_model = "claude-sonnet-4-6"
                mock_settings.repo_path = FIXTURE_REPO
                result = await code_researcher_node(state_with_plan)

        assert "doc_context" in result
        assert "implementation_summary" in result["doc_context"]
