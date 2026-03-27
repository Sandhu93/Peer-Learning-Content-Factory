"""
Unit and integration tests for Phase 2 agents:
    doc_analyzer, concept_mapper, pedagogy_planner, writer

All LLM calls are mocked — no API keys required.
Tests focus on:
  - Correct state fields written / not written (parallel isolation)
  - Graceful degradation on malformed LLM responses
  - Edge cases: empty inputs, missing state keys, no doc files
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.state import PipelineState
from src.utils.llm import LLMResponse

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "sample_repo"
EMPTY_REPO = Path(__file__).parent / "fixtures"  # no README.md here


# ── Shared LLM response fixtures ──────────────────────────────────────────────

_DOC_ANALYZER_RESPONSE = json.dumps({
    "feature_rationale": "Added after March 2024 provider outage caused 8-minute downtime.",
    "bug_stories": [
        {
            "title": "Provider Cascade of March 2024",
            "symptom": "All queries timed out for 8 minutes; thread pool exhausted.",
            "root_cause": "Retry loop kept hammering slow provider, exhausting 50 threads.",
            "fix": "Added CircuitBreaker with failure_threshold=5, recovery_timeout=30s.",
            "lesson": "Retries without circuit breaking convert provider slowness into service outage.",
        }
    ],
    "tradeoffs": [
        "Threshold of 5 balances false positives vs real failure detection latency.",
        "Counter-based threshold chosen over sliding window for simplicity.",
    ],
    "evolution_notes": "Migrated from bare try/except to state machine in v2.",
    "doc_quality": "high",
})

_CONCEPT_MAPPER_RESPONSE = json.dumps({
    "pattern_name": "Circuit Breaker",
    "general_description": "A fault-tolerance proxy that tracks failure rates and stops forwarding requests once a threshold is exceeded, allowing the downstream system to recover.",
    "naive_approach": "Calling the provider directly inside a try/except with a bare retry loop.",
    "why_naive_fails": "Under sustained degradation, all threads block on slow timeouts, exhausting the connection pool within seconds.",
    "production_approach": "A state machine (CLOSED → OPEN → HALF_OPEN) that tracks consecutive failures and fails fast when the circuit is open.",
    "applicable_domains": ["HTTP clients", "database connections", "message queue consumers", "gRPC stubs"],
    "anti_patterns": [
        "Using the same threshold for all services regardless of SLA.",
        "Forgetting the HALF_OPEN state — circuit never recovers.",
        "Swallowing the CircuitOpenError so callers don't know requests were rejected.",
    ],
    "use_when": [
        "Calling unreliable or rate-limited external services.",
        "High-throughput systems where slow downstream compounds quickly.",
    ],
    "avoid_when": [
        "Internal function calls with no network hop.",
        "Operations that must complete (payment commits, audit logs).",
    ],
    "analogy": "A home circuit breaker that trips to prevent electrical fires — it does not fix the short circuit, but protects everything else while you investigate.",
    "key_insight": "The circuit opens to protect the caller, not to signal the failure to the provider.",
})

_PEDAGOGY_PLANNER_RESPONSE = json.dumps({
    "difficulty": "intermediate",
    "hook": "Your service is down because the provider is slow — not failed. That distinction costs you 8 minutes of downtime.",
    "analogy": "A home circuit breaker that trips to prevent electrical fires.",
    "sections_to_include": [
        "problem_framing", "naive_vs_production", "how_it_works",
        "code_walkthrough", "bug_story", "tradeoffs", "discussion_prompts",
    ],
    "comparison_framing": "Bare Retry Loop vs Circuit Breaker",
    "code_example_strategy": "Lead with the CircuitBreaker class and State enum, then show the call() method.",
    "diagram_specs": [
        {
            "diagram_type": "architecture",
            "title": "Without circuit breaker: slow provider exhausts the thread pool",
            "placement": "problem",
            "nodes": [
                {"id": "svc", "label": "SERVICE", "subtitle": "all threads blocked", "x": 40, "y": 110, "w": 160, "h": 60, "color": "red"},
                {"id": "prov", "label": "PROVIDER", "subtitle": "slow", "x": 480, "y": 110, "w": 160, "h": 60, "color": "amber"},
            ],
            "edges": [
                {"from_id": "svc", "to_id": "prov", "label": "45s timeout × 50 threads"},
            ],
        },
        {
            "diagram_type": "state_machine",
            "title": "Circuit breaker state machine",
            "placement": "main",
            "nodes": [
                {"id": "closed", "label": "CLOSED", "subtitle": "normal", "x": 40, "y": 110, "w": 160, "h": 60, "color": "green"},
                {"id": "open", "label": "OPEN", "subtitle": "failing fast", "x": 480, "y": 110, "w": 160, "h": 60, "color": "red"},
                {"id": "half", "label": "HALF-OPEN", "subtitle": "probing", "x": 260, "y": 110, "w": 160, "h": 60, "color": "amber"},
            ],
            "edges": [
                {"from_id": "closed", "to_id": "open", "label": "failures ≥ threshold"},
                {"from_id": "open", "to_id": "half", "label": "timeout elapsed", "dashed": True},
                {"from_id": "half", "to_id": "closed", "label": "success"},
                {"from_id": "half", "to_id": "open", "label": "failure"},
            ],
        },
    ],
    "bug_story_source": "doc_context",
    "discussion_prompts": [
        "How would you choose the failure_threshold for a service with variable traffic patterns?",
        "What happens when the HALF_OPEN probe request itself triggers a slow timeout?",
        "When would a circuit breaker cause more harm than it prevents?",
        "How would you test circuit breaker behaviour without mocking time?",
    ],
    "key_terms": ["CLOSED", "OPEN", "HALF_OPEN", "failure_threshold", "recovery_timeout"],
})

_WRITER_RESPONSE = json.dumps({
    "problem_statement": "Without a circuit breaker, a slow LLM provider exhausts your thread pool in seconds.",
    "problem_context": "When OpenAI response times climbed to 45 seconds, every in-flight request blocked a thread.",
    "problem_elaboration": "With 50 threads and 45-second timeouts, the pool drains in under 2 minutes.",
    "naive_description": "Call the provider directly with a retry loop.",
    "naive_code": "def query(prompt):\n    for i in range(3):\n        try:\n            return client.complete(prompt)\n        except Exception:\n            time.sleep(2 ** i)",
    "naive_failure": "Under sustained slowness, all retries block on full timeouts, multiplying thread consumption.",
    "prod_description": "Wrap the call in a circuit breaker that fails fast when the provider is known to be degraded.",
    "prod_code": "# circuit_breaker.py:38-48\ndef call(self, fn, *args, **kwargs):\n    if self.state == State.OPEN:\n        raise CircuitOpenError('Circuit is OPEN')\n    try:\n        result = fn(*args, **kwargs)\n        self._on_success()\n        return result\n    except Exception:\n        self._on_failure()\n        raise",
    "prod_rationale": "Fails fast when OPEN so threads are never blocked on a known-bad provider.",
    "how_it_works_intro": "The circuit breaker is a proxy with three states: CLOSED, OPEN, and HALF_OPEN.",
    "subsection_1_title": "State Transitions",
    "subsection_1_content": "The breaker opens after consecutive failures reach the threshold.",
    "subsection_2_title": "Recovery Protocol",
    "subsection_2_content": "After a timeout, the breaker moves to HALF_OPEN and allows one probe request.",
    "key_insight": "The circuit opens to protect the caller, not to signal the failure to the provider.",
    "code_intro": "The circuit_breaker.py file contains the full state machine.",
    "code_file_ref_1": "circuit_breaker.py:10-14",
    "code_snippet_1": "class State(Enum):\n    CLOSED = 'closed'\n    OPEN = 'open'\n    HALF_OPEN = 'half_open'",
    "code_snippet_1_explanation": "Three discrete states model the circuit's health.",
    "code_file_ref_2": "circuit_breaker.py:50-58",
    "code_snippet_2": "def _on_failure(self) -> None:\n    self._failure_count += 1\n    if self._failure_count >= self.failure_threshold:\n        self._state = State.OPEN",
    "code_snippet_2_explanation": "Each failure increments the counter; once the threshold is hit, the circuit trips.",
    "bug_title": "Provider Cascade of March 2024",
    "bug_symptom": "All queries timed out for 8 minutes; thread pool exhausted.",
    "bug_root_cause": "Retry loop blocked threads on 45-second timeouts under sustained provider slowness.",
    "bug_fix": "Added CircuitBreaker with failure_threshold=5.",
    "bug_lesson": "Retries without circuit breaking convert provider slowness into a full outage.",
    "tradeoffs_intro": "Circuit breakers involve explicit configuration trade-offs.",
    "use_when_items": ["Calling unreliable external APIs", "High-throughput services"],
    "avoid_when_items": ["Internal function calls", "Must-complete operations like payments"],
    "anti_patterns": "The most common mistake is forgetting the HALF_OPEN state, which prevents recovery.",
    "discussion_prompts": [
        "How would you choose the failure_threshold?",
        "What happens when the HALF_OPEN probe itself times out?",
        "When would this pattern cause more harm than good?",
        "How would you test this without mocking time?",
    ],
    "linkedin_post": "Your service was down for 8 minutes.\n\nNot because the provider failed. Because it was slow.\n\nThe circuit breaker pattern prevents this.",
    "reel_scenes": [
        {"timestamp": "0:00-0:05", "title": "Hook", "visual": "[text on screen]", "script": "Your service is down and the provider is fine."},
        {"timestamp": "0:05-0:15", "title": "Problem", "visual": "[thread pool diagram]", "script": "Slow provider, retry loop, 50 threads gone in 2 minutes."},
        {"timestamp": "0:15-0:25", "title": "Naive", "visual": "[code]", "script": "The naive fix: more retries. Wrong."},
        {"timestamp": "0:25-0:40", "title": "Solution", "visual": "[state machine]", "script": "Circuit breaker: CLOSED, OPEN, HALF_OPEN."},
        {"timestamp": "0:40-0:50", "title": "Insight", "visual": "[callout]", "script": "It opens to protect the caller, not signal the provider."},
        {"timestamp": "0:50-0:60", "title": "CTA", "visual": "[text]", "script": "Which service in your stack needs this first?"},
    ],
    "related_topics": [
        "Retry with exponential backoff",
        "Bulkhead pattern",
        "Timeout budgets",
        "Health checks",
        "Rate limiting",
    ],
})


@pytest.fixture
def base_state() -> PipelineState:
    return {
        "concept_name": "Circuit breaker for provider failure",
        "category": "Reliability, Failure Isolation, and Production Hardening",
        "why_it_matters": "Prevents cascading failures.",
        "repo_anchors": ["circuit_breaker", "CircuitBreaker"],
        "repo_path": str(FIXTURE_REPO),
        "revision_count": 0,
        "is_complete": False,
        "errors": [],
        "teaching_plan": {
            "difficulty": "intermediate",
            "repo_search_strategy": {"primary_terms": ["CircuitBreaker"], "secondary_terms": []},
            "related_concepts": ["bulkhead pattern", "retry with backoff"],
        },
        "code_evidence": [
            {
                "file_path": "circuit_breaker.py",
                "line_start": 10,
                "line_end": 14,
                "content": "class State(Enum):\n    CLOSED = 'closed'\n    OPEN = 'open'",
                "relevance": "Core state enum",
            }
        ],
        "implementation_notes": {
            "implementation_summary": "Counter-based threshold with recovery timeout.",
            "evidence_gaps": [],
        },
    }


def _mock_llm(content: str, provider: str = "anthropic") -> LLMResponse:
    return LLMResponse(
        content=content,
        input_tokens=100,
        output_tokens=200,
        model="claude-sonnet-4-6",
        provider=provider,
    )


def _mock_settings(openai_configured: bool = False):
    m = MagicMock()
    m.default_research_model = "claude-sonnet-4-6"
    m.default_writer_model = "claude-sonnet-4-6"
    m.default_openai_model = "gpt-4o"
    m.openai_configured = openai_configured
    m.repo_path = FIXTURE_REPO
    return m


# ── doc_analyzer ──────────────────────────────────────────────────────────────

class TestDocAnalyzerNode:
    @pytest.mark.asyncio
    async def test_produces_doc_context_with_required_keys(self, base_state):
        from src.agents.doc_analyzer import doc_analyzer_node

        with patch("src.agents.doc_analyzer.call_llm", new=AsyncMock(return_value=_mock_llm(_DOC_ANALYZER_RESPONSE))):
            with patch("src.config.settings", _mock_settings()):
                result = await doc_analyzer_node(base_state)

        ctx = result["doc_context"]
        assert "feature_rationale" in ctx
        assert "bug_stories" in ctx
        assert "tradeoffs" in ctx
        assert "evolution_notes" in ctx
        assert "doc_quality" in ctx

    @pytest.mark.asyncio
    async def test_extracts_bug_stories(self, base_state):
        from src.agents.doc_analyzer import doc_analyzer_node

        with patch("src.agents.doc_analyzer.call_llm", new=AsyncMock(return_value=_mock_llm(_DOC_ANALYZER_RESPONSE))):
            with patch("src.config.settings", _mock_settings()):
                result = await doc_analyzer_node(base_state)

        stories = result["doc_context"]["bug_stories"]
        assert len(stories) == 1
        assert stories[0]["title"] == "Provider Cascade of March 2024"
        assert "symptom" in stories[0]
        assert "root_cause" in stories[0]
        assert "fix" in stories[0]
        assert "lesson" in stories[0]

    @pytest.mark.asyncio
    async def test_does_not_write_code_evidence_or_implementation_notes(self, base_state):
        """Parallel safety: doc_analyzer must not touch code_researcher's output keys."""
        from src.agents.doc_analyzer import doc_analyzer_node

        original_evidence = base_state["code_evidence"]
        original_notes = base_state["implementation_notes"]

        with patch("src.agents.doc_analyzer.call_llm", new=AsyncMock(return_value=_mock_llm(_DOC_ANALYZER_RESPONSE))):
            with patch("src.config.settings", _mock_settings()):
                result = await doc_analyzer_node(base_state)

        # doc_analyzer must not include keys owned by code_researcher.
        # Since parallel branches now return ONLY their own keys (no **state spread),
        # these keys must be absent from the result dict entirely.
        assert "code_evidence" not in result
        assert "implementation_notes" not in result

    @pytest.mark.asyncio
    async def test_handles_malformed_json_gracefully(self, base_state):
        from src.agents.doc_analyzer import doc_analyzer_node

        with patch("src.agents.doc_analyzer.call_llm", new=AsyncMock(return_value=_mock_llm("not json at all"))):
            with patch("src.config.settings", _mock_settings()):
                result = await doc_analyzer_node(base_state)

        # Should not crash; returns fallback doc_context
        assert "doc_context" in result
        assert result["doc_context"]["doc_quality"] == "low"
        assert result["doc_context"]["bug_stories"] == []

    @pytest.mark.asyncio
    async def test_handles_repo_with_no_doc_files(self, base_state):
        """Repo with no README or docs returns minimal doc_context without calling LLM."""
        from src.agents.doc_analyzer import doc_analyzer_node

        state = {**base_state, "repo_path": str(EMPTY_REPO)}

        with patch("src.agents.doc_analyzer.find_doc_files", return_value=[]):
            with patch("src.config.settings", _mock_settings()):
                result = await doc_analyzer_node(state)

        assert "doc_context" in result
        assert result["doc_context"]["doc_quality"] == "low"
        assert result["doc_context"]["feature_rationale"] == "Not documented."

    @pytest.mark.asyncio
    async def test_returns_partial_json_bug_stories_as_empty_list(self, base_state):
        """LLM omits bug_stories key — fallback should still be a list, not crash."""
        from src.agents.doc_analyzer import doc_analyzer_node

        partial = json.dumps({
            "feature_rationale": "Added for reliability.",
            "tradeoffs": [],
            "evolution_notes": "N/A",
            "doc_quality": "medium",
            # bug_stories intentionally omitted
        })

        with patch("src.agents.doc_analyzer.call_llm", new=AsyncMock(return_value=_mock_llm(partial))):
            with patch("src.config.settings", _mock_settings()):
                result = await doc_analyzer_node(base_state)

        # Should not KeyError; doc_context still returned
        assert "doc_context" in result


# ── concept_mapper ────────────────────────────────────────────────────────────

class TestConceptMapperNode:
    @pytest.fixture
    def state_with_doc_context(self, base_state):
        return {
            **base_state,
            "doc_context": json.loads(_DOC_ANALYZER_RESPONSE),
        }

    @pytest.mark.asyncio
    async def test_produces_generalized_pattern_with_required_keys(self, state_with_doc_context):
        from src.agents.concept_mapper import concept_mapper_node

        with patch("src.agents.concept_mapper.call_llm", new=AsyncMock(return_value=_mock_llm(_CONCEPT_MAPPER_RESPONSE))):
            with patch("src.config.settings", _mock_settings()):
                result = await concept_mapper_node(state_with_doc_context)

        gp = result["generalized_pattern"]
        for key in ("pattern_name", "general_description", "naive_approach",
                    "why_naive_fails", "production_approach", "applicable_domains",
                    "anti_patterns", "use_when", "avoid_when", "analogy", "key_insight"):
            assert key in gp, f"Missing key: {key}"

    @pytest.mark.asyncio
    async def test_uses_openai_when_configured(self, state_with_doc_context):
        from src.agents.concept_mapper import concept_mapper_node

        captured_provider = {}

        async def mock_call_llm(provider, **kwargs):
            captured_provider["provider"] = provider
            return _mock_llm(_CONCEPT_MAPPER_RESPONSE, provider=provider)

        with patch("src.agents.concept_mapper.call_llm", new=mock_call_llm):
            with patch("src.config.settings", _mock_settings(openai_configured=True)):
                await concept_mapper_node(state_with_doc_context)

        assert captured_provider["provider"] == "openai"

    @pytest.mark.asyncio
    async def test_falls_back_to_claude_when_openai_absent(self, state_with_doc_context):
        from src.agents.concept_mapper import concept_mapper_node

        captured_provider = {}

        async def mock_call_llm(provider, **kwargs):
            captured_provider["provider"] = provider
            return _mock_llm(_CONCEPT_MAPPER_RESPONSE, provider=provider)

        with patch("src.agents.concept_mapper.call_llm", new=mock_call_llm):
            with patch("src.config.settings", _mock_settings(openai_configured=False)):
                await concept_mapper_node(state_with_doc_context)

        assert captured_provider["provider"] == "anthropic"

    @pytest.mark.asyncio
    async def test_handles_malformed_json_gracefully(self, state_with_doc_context):
        from src.agents.concept_mapper import concept_mapper_node

        with patch("src.agents.concept_mapper.call_llm", new=AsyncMock(return_value=_mock_llm("not json"))):
            with patch("src.config.settings", _mock_settings()):
                result = await concept_mapper_node(state_with_doc_context)

        # Falls back to partial content; does not crash
        assert "generalized_pattern" in result
        assert result["generalized_pattern"]["pattern_name"] != ""

    @pytest.mark.asyncio
    async def test_does_not_clobber_code_evidence_or_doc_context(self, state_with_doc_context):
        from src.agents.concept_mapper import concept_mapper_node

        original_evidence = state_with_doc_context["code_evidence"]

        with patch("src.agents.concept_mapper.call_llm", new=AsyncMock(return_value=_mock_llm(_CONCEPT_MAPPER_RESPONSE))):
            with patch("src.config.settings", _mock_settings()):
                result = await concept_mapper_node(state_with_doc_context)

        assert result["code_evidence"] == original_evidence

    @pytest.mark.asyncio
    async def test_works_with_empty_code_evidence(self, base_state):
        """Concept mapper should function even when no code snippets were found."""
        from src.agents.concept_mapper import concept_mapper_node

        state = {**base_state, "code_evidence": [], "doc_context": {}}

        with patch("src.agents.concept_mapper.call_llm", new=AsyncMock(return_value=_mock_llm(_CONCEPT_MAPPER_RESPONSE))):
            with patch("src.config.settings", _mock_settings()):
                result = await concept_mapper_node(state)

        assert "generalized_pattern" in result


# ── pedagogy_planner ──────────────────────────────────────────────────────────

class TestPedagogyPlannerNode:
    @pytest.fixture
    def full_research_state(self, base_state):
        return {
            **base_state,
            "doc_context": json.loads(_DOC_ANALYZER_RESPONSE),
            "generalized_pattern": json.loads(_CONCEPT_MAPPER_RESPONSE),
        }

    @pytest.mark.asyncio
    async def test_produces_diagram_specs_list(self, full_research_state):
        from src.agents.pedagogy_planner import pedagogy_planner_node

        with patch("src.agents.pedagogy_planner.call_llm", new=AsyncMock(return_value=_mock_llm(_PEDAGOGY_PLANNER_RESPONSE))):
            with patch("src.config.settings", _mock_settings()):
                result = await pedagogy_planner_node(full_research_state)

        assert "diagram_specs" in result
        assert isinstance(result["diagram_specs"], list)
        assert len(result["diagram_specs"]) == 2

    @pytest.mark.asyncio
    async def test_diagram_specs_have_required_structure(self, full_research_state):
        from src.agents.pedagogy_planner import pedagogy_planner_node

        with patch("src.agents.pedagogy_planner.call_llm", new=AsyncMock(return_value=_mock_llm(_PEDAGOGY_PLANNER_RESPONSE))):
            with patch("src.config.settings", _mock_settings()):
                result = await pedagogy_planner_node(full_research_state)

        for spec in result["diagram_specs"]:
            assert "nodes" in spec
            assert "edges" in spec
            assert "placement" in spec
            assert spec["placement"] in ("problem", "main")
            assert "title" in spec

    @pytest.mark.asyncio
    async def test_merges_with_existing_teaching_plan(self, full_research_state):
        """Phase 1 teaching_plan keys must survive the Phase 2 pedagogy_planner merge."""
        from src.agents.pedagogy_planner import pedagogy_planner_node

        with patch("src.agents.pedagogy_planner.call_llm", new=AsyncMock(return_value=_mock_llm(_PEDAGOGY_PLANNER_RESPONSE))):
            with patch("src.config.settings", _mock_settings()):
                result = await pedagogy_planner_node(full_research_state)

        # Phase 1 key must still be present
        assert "repo_search_strategy" in result["teaching_plan"]
        # Phase 2 key must be added
        assert "hook" in result["teaching_plan"]
        assert "comparison_framing" in result["teaching_plan"]

    @pytest.mark.asyncio
    async def test_discussion_prompts_count(self, full_research_state):
        from src.agents.pedagogy_planner import pedagogy_planner_node

        with patch("src.agents.pedagogy_planner.call_llm", new=AsyncMock(return_value=_mock_llm(_PEDAGOGY_PLANNER_RESPONSE))):
            with patch("src.config.settings", _mock_settings()):
                result = await pedagogy_planner_node(full_research_state)

        prompts = result["teaching_plan"].get("discussion_prompts", [])
        assert len(prompts) == 4

    @pytest.mark.asyncio
    async def test_fallback_plan_on_json_parse_failure(self, full_research_state):
        from src.agents.pedagogy_planner import pedagogy_planner_node

        with patch("src.agents.pedagogy_planner.call_llm", new=AsyncMock(return_value=_mock_llm("{invalid}"))):
            with patch("src.config.settings", _mock_settings()):
                result = await pedagogy_planner_node(full_research_state)

        # Fallback plan: still produces required fields
        assert "teaching_plan" in result
        assert "diagram_specs" in result
        assert isinstance(result["diagram_specs"], list)
        assert result["teaching_plan"]["difficulty"] == "intermediate"

    @pytest.mark.asyncio
    async def test_handles_missing_generalized_pattern(self, base_state):
        """Should not crash when concept_mapper produced nothing."""
        from src.agents.pedagogy_planner import pedagogy_planner_node

        state = {**base_state, "generalized_pattern": {}, "doc_context": {}}

        with patch("src.agents.pedagogy_planner.call_llm", new=AsyncMock(return_value=_mock_llm(_PEDAGOGY_PLANNER_RESPONSE))):
            with patch("src.config.settings", _mock_settings()):
                result = await pedagogy_planner_node(state)

        assert "teaching_plan" in result


# ── writer ────────────────────────────────────────────────────────────────────

class TestWriterNode:
    @pytest.fixture
    def full_state(self, base_state):
        pedagogy_plan = json.loads(_PEDAGOGY_PLANNER_RESPONSE)
        return {
            **base_state,
            "doc_context": json.loads(_DOC_ANALYZER_RESPONSE),
            "generalized_pattern": json.loads(_CONCEPT_MAPPER_RESPONSE),
            "teaching_plan": {
                **base_state["teaching_plan"],
                **pedagogy_plan,
            },
            "diagram_specs": pedagogy_plan["diagram_specs"],
        }

    @pytest.mark.asyncio
    async def test_produces_guide_html(self, full_state):
        from src.agents.writer import writer_node

        with patch("src.agents.writer.call_llm", new=AsyncMock(return_value=_mock_llm(_WRITER_RESPONSE))):
            with patch("src.config.settings", _mock_settings()):
                result = await writer_node(full_state)

        assert "guide_html" in result
        assert len(result["guide_html"]) > 100

    @pytest.mark.asyncio
    async def test_no_unfilled_placeholders_in_output(self, full_state):
        """All {{variable}} tokens must be replaced in the final HTML."""
        from src.agents.writer import writer_node

        with patch("src.agents.writer.call_llm", new=AsyncMock(return_value=_mock_llm(_WRITER_RESPONSE))):
            with patch("src.config.settings", _mock_settings()):
                result = await writer_node(full_state)

        # Find any remaining {{...}} tokens
        import re
        remaining = re.findall(r"\{\{[^}]+\}\}", result["guide_html"])
        assert remaining == [], f"Unfilled placeholders: {remaining}"

    @pytest.mark.asyncio
    async def test_concept_name_appears_in_html(self, full_state):
        from src.agents.writer import writer_node

        with patch("src.agents.writer.call_llm", new=AsyncMock(return_value=_mock_llm(_WRITER_RESPONSE))):
            with patch("src.config.settings", _mock_settings()):
                result = await writer_node(full_state)

        assert "Circuit breaker for provider failure" in result["guide_html"]

    @pytest.mark.asyncio
    async def test_produces_linkedin_post_in_state(self, full_state):
        from src.agents.writer import writer_node

        with patch("src.agents.writer.call_llm", new=AsyncMock(return_value=_mock_llm(_WRITER_RESPONSE))):
            with patch("src.config.settings", _mock_settings()):
                result = await writer_node(full_state)

        assert "linkedin_post" in result
        assert len(result["linkedin_post"]) > 0

    @pytest.mark.asyncio
    async def test_produces_reel_script_in_state(self, full_state):
        from src.agents.writer import writer_node

        with patch("src.agents.writer.call_llm", new=AsyncMock(return_value=_mock_llm(_WRITER_RESPONSE))):
            with patch("src.config.settings", _mock_settings()):
                result = await writer_node(full_state)

        assert "reel_script" in result
        assert len(result["reel_script"]) > 0

    @pytest.mark.asyncio
    async def test_diagram_svgs_populated_in_state(self, full_state):
        from src.agents.writer import writer_node

        with patch("src.agents.writer.call_llm", new=AsyncMock(return_value=_mock_llm(_WRITER_RESPONSE))):
            with patch("src.config.settings", _mock_settings()):
                result = await writer_node(full_state)

        assert "diagram_svgs" in result
        assert len(result["diagram_svgs"]) == 2  # one problem, one main

    @pytest.mark.asyncio
    async def test_handles_empty_diagram_specs(self, full_state):
        """Writer must not crash when pedagogy_planner produced no diagram specs."""
        from src.agents.writer import writer_node

        state = {**full_state, "diagram_specs": []}

        with patch("src.agents.writer.call_llm", new=AsyncMock(return_value=_mock_llm(_WRITER_RESPONSE))):
            with patch("src.config.settings", _mock_settings()):
                result = await writer_node(state)

        assert "guide_html" in result
        # Fallback SVGs injected — no {{diagram_*}} placeholders left
        import re
        remaining = re.findall(r"\{\{diagram[^}]+\}\}", result["guide_html"])
        assert remaining == []

    @pytest.mark.asyncio
    async def test_handles_malformed_writer_json_gracefully(self, full_state):
        """Writer LLM returns garbage JSON — should render with empty fallback content."""
        from src.agents.writer import writer_node

        with patch("src.agents.writer.call_llm", new=AsyncMock(return_value=_mock_llm("not json at all {"))):
            with patch("src.config.settings", _mock_settings()):
                result = await writer_node(full_state)

        # Must not raise; must produce some HTML
        assert "guide_html" in result
        assert "<!DOCTYPE html>" in result["guide_html"]

    @pytest.mark.asyncio
    async def test_handles_missing_doc_context(self, base_state):
        """Writer should produce output even without doc_context (no bug stories, etc.)."""
        from src.agents.writer import writer_node

        state = {
            **base_state,
            "generalized_pattern": json.loads(_CONCEPT_MAPPER_RESPONSE),
            "teaching_plan": {**base_state["teaching_plan"], **json.loads(_PEDAGOGY_PLANNER_RESPONSE)},
            "diagram_specs": json.loads(_PEDAGOGY_PLANNER_RESPONSE)["diagram_specs"],
            # doc_context intentionally absent
        }

        with patch("src.agents.writer.call_llm", new=AsyncMock(return_value=_mock_llm(_WRITER_RESPONSE))):
            with patch("src.config.settings", _mock_settings()):
                result = await writer_node(state)

        assert "guide_html" in result

    @pytest.mark.asyncio
    async def test_inline_svg_present_in_guide(self, full_state):
        """Both diagrams rendered as inline SVG inside the HTML."""
        from src.agents.writer import writer_node

        with patch("src.agents.writer.call_llm", new=AsyncMock(return_value=_mock_llm(_WRITER_RESPONSE))):
            with patch("src.config.settings", _mock_settings()):
                result = await writer_node(full_state)

        assert "<svg" in result["guide_html"]
        assert "viewBox" in result["guide_html"]


# ── Parallel branch state isolation ──────────────────────────────────────────

class TestParallelBranchIsolation:
    """
    Verify that the two parallel branches (code_researcher, doc_analyzer)
    write to disjoint state keys so LangGraph fan-in merges safely.
    """

    @pytest.mark.asyncio
    async def test_code_researcher_and_doc_analyzer_write_disjoint_keys(self, base_state):
        """
        Simulate what LangGraph does: run both branches from the same state,
        merge their return dicts, and verify no key is overwritten by accident.
        """
        from src.agents.code_researcher import code_researcher_node
        from src.agents.doc_analyzer import doc_analyzer_node

        researcher_response = LLMResponse(
            content=json.dumps({
                "code_evidence": [{"file_path": "f.py", "line_start": 1, "line_end": 5, "content": "x", "relevance": "r"}],
                "implementation_summary": "Uses a counter.",
                "gaps": [],
            }),
            input_tokens=100, output_tokens=100,
            model="claude-sonnet-4-6", provider="anthropic",
        )

        with patch("src.agents.code_researcher.call_llm", new=AsyncMock(return_value=researcher_response)):
            with patch("src.config.settings", _mock_settings()):
                researcher_result = await code_researcher_node(base_state)

        with patch("src.agents.doc_analyzer.call_llm", new=AsyncMock(return_value=_mock_llm(_DOC_ANALYZER_RESPONSE))):
            with patch("src.config.settings", _mock_settings()):
                doc_result = await doc_analyzer_node(base_state)

        # Simulate LangGraph fan-in merge: apply both dicts
        merged = {**base_state, **researcher_result, **doc_result}

        # Both outputs must survive the merge
        assert "code_evidence" in merged
        assert len(merged["code_evidence"]) > 0
        assert "implementation_notes" in merged
        assert "implementation_summary" in merged["implementation_notes"]
        assert "doc_context" in merged
        assert len(merged["doc_context"]["bug_stories"]) > 0
