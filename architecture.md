# Architecture

This document describes the structure, data flow, and component responsibilities of the Peer Learning Content Factory. It is updated whenever the system design changes in a meaningful way.

**Last updated:** 2026-03-27
**Current phase:** Phase 1 complete — research pipeline (topic_parser + code_researcher)

---

## System Overview

The system takes a concept name from a markdown backlog, researches it against a local codebase, and produces a content bundle (HTML guide, LinkedIn post, reel script, diagrams). It is structured as an **LangGraph agent pipeline** where each agent is a discrete node with a single responsibility.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Input Layer                              │
│  peer_learning_concepts.md    +    REPO_PATH (local codebase)   │
└────────────────────┬──────────────────────┬────────────────────┘
                     │                      │
                     ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Research Pipeline                           │
│                                                                 │
│   [topic_parser] ──────────────────────────────────────────┐   │
│        │                                                    │   │
│        ├──→ [code_researcher]  (searches codebase)          │   │
│        ├──→ [doc_analyzer]     (reads README, bugs.md, ADR) │   │
│        └──→ [concept_mapper]   (generalizes the pattern)    │   │
│                          │ │ │                              │   │
│                          └─┴─┘ ← fan-in                    │   │
│                              │                              │   │
│                              ▼                              │   │
│                    [pedagogy_planner]                        │   │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                     Content Pipeline                            │
│                                                                 │
│          ┌──────────────┬───────────────┐                       │
│          ▼              ▼               ▼                       │
│       [writer]  [linkedin_writer]  [reel_writer]                │
│          │              │               │                       │
│          └──────────────┴───────────────┘                       │
│                         │                                       │
│               [diagram_generator]                               │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                     Quality Pipeline                            │
│                                                                 │
│               [tech_reviewer]                                   │
│                /           \                                    │
│         accurate?         not accurate                          │
│              │                  └──→ back to [writer]           │
│              ▼                                                  │
│          [editor]                                               │
│              │                                                  │
│      [human review] ←─ --interactive mode                      │
│         /       \                                               │
│      approve    revise ──→ back to [pedagogy_planner]           │
│         │                                                       │
│    [save_outputs]                                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Pipeline State

All agents share a single `PipelineState` TypedDict. The state starts sparse (only concept name + category) and accumulates data as it passes through each node.

```
PipelineState
│
├── Input (set at CLI entry point)
│   ├── concept_name: str
│   ├── category: str
│   ├── why_it_matters: str
│   ├── repo_anchors: list[str]          # search terms from backlog
│   └── repo_path: str                   # resolved once; travels with run
│
├── Research outputs (set by Phase 1/2 agents)
│   ├── code_evidence: list[CodeSnippet] # matched code from repo
│   ├── doc_context: dict                # narrative from docs/README/bugs
│   └── generalized_pattern: dict       # abstracted SE pattern
│
├── Planning (set by pedagogy_planner)
│   ├── teaching_plan: dict              # structure, difficulty, sections
│   └── diagram_specs: list[DiagramSpec]
│
├── Content drafts (set by writer agents)
│   ├── guide_html: str
│   ├── linkedin_post: str
│   ├── reel_script: str
│   └── diagram_svgs: list[str]
│
├── Review (set by reviewer/editor)
│   ├── review_result: dict
│   ├── editor_result: dict
│   └── revision_count: int
│
└── Control
    ├── is_complete: bool
    ├── output_path: str
    └── errors: list[str]
```

Sub-models (`CodeSnippet`, `BugStory`, `DiagramSpec`) are Pydantic `BaseModel` classes defined in `src/state.py`. They are serialised to `dict` for storage in the TypedDict but validated with Pydantic before use.

---

## Agent Responsibilities

### Phase 1 — Research

| Agent | Model | Temp | Input | Output |
|---|---|---|---|---|
| `topic_parser` | Claude Sonnet | 0.0 | concept name, category, anchors | enriched fact sheet (difficulty, prereqs, search strategy) |
| `code_researcher` | Claude Sonnet | 0.0 | search strategy, repo | `code_evidence[]`, implementation summary |
| `doc_analyzer` | Claude Sonnet | 0.0 | README, bugs.md, arch docs | `doc_context` (rationale, bug stories, tradeoffs) |
| `concept_mapper` | GPT-4o | 0.3 | code evidence + doc context | `generalized_pattern` (portable SE pattern) |

### Phase 2 — Planning + Writing

| Agent | Model | Temp | Input | Output |
|---|---|---|---|---|
| `pedagogy_planner` | Claude Sonnet | 0.2 | full fact sheet | `teaching_plan`, `diagram_specs` |
| `writer` | Claude Opus/Sonnet | 0.3 | teaching plan + all evidence + HTML template | `guide_html` |
| `linkedin_writer` | Claude Sonnet | 0.5 | fact sheet + guide | `linkedin_post` |
| `reel_writer` | GPT-4o | 0.5 | fact sheet | `reel_script` |
| `diagram_generator` | Claude Sonnet | 0.0 | `DiagramSpec[]` | `diagram_svgs[]` |

### Phase 3 — Quality Gate

| Agent | Model | Temp | Input | Output |
|---|---|---|---|---|
| `tech_reviewer` | Claude Sonnet | 0.0 | guide HTML + codebase access | `review_result` (is_accurate, corrections) |
| `editor` | Claude Sonnet | 0.2 | reviewed guide HTML | `editor_result`, polished HTML |

---

## Tool Layer

Tools are functions the agents call during their work. They have **no LLM calls** — they are pure I/O operations against the local filesystem.

```
src/tools/
├── code_search.py      — ripgrep wrapper
│   ├── search_term(term, repo_path)         → list[match]
│   ├── search_pattern(pattern, repo_path)   → list[match]
│   ├── find_tests(concept_name, repo_path)  → list[match]
│   ├── read_file_range(path, start, end)    → str
│   └── list_files(repo_path, glob)          → list[str]
│
├── file_reader.py      — Python AST-based extraction
│   ├── read_file(path)                      → str
│   ├── extract_function(path, fn_name)      → str | None
│   ├── extract_class(path, class_name)      → str | None
│   ├── find_doc_files(repo_path)            → list[Path]
│   └── read_doc_file(path)                  → str
│
└── repo_manifest.py    — repo structure overview
    └── build_manifest(repo_path)            → str  (tree + stats)
```

`code_search.py` uses ripgrep when available and falls back to `Path.rglob()` otherwise (see BUG-002).

---

## LLM Abstraction

All LLM calls go through `src/utils/llm.py`:

```
call_llm(provider, model, system_prompt, user_message, temperature)
    │
    ├── provider="anthropic" → anthropic.AsyncAnthropic client
    │       → claude-sonnet-4-6 / claude-opus-4-6 / claude-haiku-4-5
    │
    └── provider="openai"    → openai.AsyncOpenAI client
            → gpt-4o / gpt-4o-mini

Returns: LLMResponse(content, input_tokens, output_tokens, model, provider)
```

Retry logic: up to 2 retries with exponential backoff (1s, 2s). On retry, the previous error message is appended to the prompt as context.

---

## Template System

The HTML guide template (`src/templates/guide_template.html`) is the single source of truth for visual design. It is **frozen** — the CSS never changes. The writer agent receives the full template in its system prompt and fills in content placeholders (`{{concept_name}}`, `{{guide_html}}`, etc.).

### Design system
| Token | Semantic meaning | Light | Dark |
|---|---|---|---|
| `--color-success` | correct / healthy / closed state | `#16a34a` | `#4ade80` |
| `--color-error` | failed / broken / open state | `#dc2626` | `#f87171` |
| `--color-warning` | degraded / half-open / caution | `#d97706` | `#fbbf24` |
| `--color-blue` | service / component nodes | `#2563eb` | `#60a5fa` |
| `--color-coral` | infrastructure nodes | `#e05c4b` | `#fb8c7f` |
| `--color-purple` | abstract concept nodes | `#7c3aed` | `#a78bfa` |

All SVG diagrams reference these via `fill="var(--color-success)"`. A single CSS toggle (`data-theme="dark"` on `<html>`) switches every color simultaneously.

---

## Output Structure

```
output/teaching_guides/
└── circuit-breaker-for-provider-failure/    ← slug from concept_name
    ├── fact_sheet.json                      ← Phase 1 output (research evidence)
    ├── guide.html                           ← Phase 2 output (full teaching guide)
    ├── linkedin.md                          ← Phase 3 output
    ├── reel_script.md                       ← Phase 3 output
    ├── metadata.json                        ← Phase 5 output
    └── diagrams/
        ├── state_machine.svg
        └── architecture.svg
```

State is persisted to `fact_sheet.json` after Phase 1 completes. If the pipeline is interrupted after Phase 1, `--resume` reads this file and continues from Phase 2 rather than restarting research.

---

## Configuration

All runtime configuration is loaded from `.env` via Pydantic Settings (`src/config.py`). The `Settings` class validates on import — a misconfigured key raises a clear error at startup, not deep inside an API call.

Critical validations:
- `ANTHROPIC_API_KEY` must be non-empty (checked in `_load_settings()`)
- `OUTPUT_PATH` is created automatically if it doesn't exist

### Repo path resolution

`REPO_PATH` is **not** validated at import time. It is a per-run input that can come from three sources, checked in priority order:

```
1. --repo CLI flag           (overrides everything)
2. REPO_PATH in .env         (default for CLI users)
3. (future) API request body (when a frontend is added)
```

Resolution happens once in `src/main.py` via `settings.effective_repo_path(override)`, which raises a `ValueError` with a clear message if none of the three sources is configured. The resolved path is placed in `PipelineState["repo_path"]` and travels with the run — agents read it from state, not from global config.

This design means two concurrent API requests can target different repos without any global state mutation. See ADR-007 and Concept 011 (`new_concepts.md`) for the full reasoning.

---

## Phase Roadmap

| Phase | Nodes added | Deliverable |
|---|---|---|
| **1 — Foundation** ✅ | `topic_parser`, `code_researcher` | `fact_sheet.json` per concept |
| **2 — Core pipeline** | `doc_analyzer`, `concept_mapper`, `pedagogy_planner`, `writer` | `guide.html` per concept |
| **3 — Content variants** | `linkedin_writer`, `reel_writer`, `diagram_generator` | Full content bundle |
| **4 — Quality gate** | `tech_reviewer`, `editor`, human-in-the-loop | Reviewed, edited guides |
| **5 — Scale** | Batch processor, index builder, cost tracker | All 80+ concepts, index.html |

Each phase adds nodes to `src/graph.py` without changing the nodes from previous phases.
