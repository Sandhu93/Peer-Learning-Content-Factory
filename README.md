# Peer Learning Content Factory

An agent orchestration system that transforms software engineering concepts into polished teaching materials — automatically.

It takes concepts from a curated backlog, researches them against a local codebase, and produces a complete content bundle per concept: a teaching guide, a LinkedIn post, a reel script, and standalone diagrams — all grounded in real code evidence from your repo.

---

## How it works

```
peer_learning_concepts.md          target codebase (REPO_PATH)
         │                                    │
         ▼                                    ▼
   [topic_parser] ──────────────── [code_researcher]
         │                         [doc_analyzer]
         │                         [concept_mapper]
         └──────────────┬──────────────────────┘
                        ▼
               [pedagogy_planner]
                        │
          ┌─────────────┼──────────────┐
          ▼             ▼              ▼
       [writer]   [linkedin_writer] [reel_writer]
          │             │              │
          └─────────────┼──────────────┘
                        ▼
               [diagram_generator]
                        │
                [tech_reviewer] ──→ corrections ──→ [writer]
                        │
                    [editor]
                        │
               [human review] (--interactive)
                        │
                  output bundle/
```

Each agent is a distinct LangGraph node with a single responsibility. The graph is built for incremental extension — Phase 1 through Phase 5 each add nodes without rewiring existing ones.

---

## Output per concept

| File | Contents |
|---|---|
| `guide.html` | Full teaching guide — inline SVG diagrams, pseudo-code, bug stories, naive-vs-production comparisons |
| `linkedin.md` | Ready-to-post LinkedIn content with hook, insight, and hashtags |
| `reel_script.md` | 60-second scene-by-scene script with visual directions |
| `diagrams/` | Standalone Mermaid and SVG files for reuse in slides or docs |
| `metadata.json` | Difficulty, prerequisites, related topics, tags |
| `fact_sheet.json` | Structured research evidence (code snippets, doc context, generalized pattern) |

---

## Technology stack

| Layer | Choice | Why |
|---|---|---|
| Orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) | Graph-based agent state machine with conditional edges and human-in-the-loop |
| Primary LLM | Anthropic Claude (`claude-sonnet-4-6`) | Long-form writing quality, strong code understanding |
| Secondary LLM | OpenAI GPT-4o | Concept abstraction and generalization |
| Code search | [ripgrep](https://github.com/BurntSushi/ripgrep) | Fast, regex-capable search across large repos |
| CLI | [Rich](https://github.com/Textualize/rich) | Progress display and formatted output |
| Config | Pydantic Settings | Type-safe env-var loading with validation |
| Python | 3.11+ | Required for `TypedDict` features used in LangGraph state |

---

## Prerequisites

- Python 3.11 or later
- An Anthropic API key (required)
- An OpenAI API key (required for concept mapper; optional if routing all calls to Claude)
- [ripgrep](https://github.com/BurntSushi/ripgrep) — for codebase search

**Install ripgrep on Windows:**
```powershell
winget install BurntSushi.ripgrep.MSVC
```

**Install ripgrep on macOS:**
```bash
brew install ripgrep
```

---

## Setup

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd peer-learning-factory

# 2. Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# 3. Install the project and dev dependencies
#    -e  = editable mode: Python imports directly from src/ so code changes
#          take effect immediately without reinstalling
#    .   = install from this directory (reads pyproject.toml)
#    [dev] = also install pytest, ruff, mypy (the "dev" optional group)
pip install -e ".[dev]"

# 4. Configure environment variables
cp .env.example .env
# Edit .env and set:
#   ANTHROPIC_API_KEY=sk-ant-...
#   OPENAI_API_KEY=sk-...
#   REPO_PATH=/absolute/path/to/the/codebase/you/want/to/analyze
```

---

## Usage

### Process a single concept
```bash
python -m src.main --concept "Circuit breaker for provider failure"
```
Produces `output/teaching_guides/circuit-breaker-for-provider-failure/fact_sheet.json` and prints the fact sheet to stdout.

### List all concepts in the backlog
```bash
python -m src.main --list
```

### Process all concepts (batch)
```bash
python -m src.main --batch
```

### Process a specific category
```bash
python -m src.main --category "Reliability, Failure Isolation, and Production Hardening"
```

### Dry run — preview without API calls
```bash
python -m src.main --batch --dry-run
```

### Resume an interrupted batch
```bash
python -m src.main --batch --resume
```
Skips concepts that already have a completed `fact_sheet.json`.

### Interactive mode (human review after each concept)
```bash
python -m src.main --concept "Circuit breaker" --interactive
```

---

## Running tests

```bash
# Run the core test suite (no API keys or ripgrep needed)
pytest tests/test_markdown_parser.py tests/test_code_search.py

# Run everything including LLM-mocked graph flow tests
pytest

# Run a specific test class
pytest tests/test_markdown_parser.py::TestFindConcept -v
```

**Test log files** are written automatically to `logs/test_YYYYMMDD_HHMMSS.log` after each run — no need to copy terminal output. Every test result (PASSED / FAILED / SKIPPED) is recorded with a full timestamp.

Tests that require `ripgrep` are marked `@needs_rg` and skip automatically when `rg` is not installed. Install ripgrep to enable them.

---

## Project structure

```
peer-learning-factory/
├── peer_learning_concepts.md     # Input: concept backlog (edit to add topics)
├── pyproject.toml                # Dependencies, pytest config, linting config
├── conftest.py                   # Pytest hooks: timestamped logs, test markers
├── .env.example                  # Copy to .env and fill in keys
│
├── src/
│   ├── config.py                 # Settings loaded from .env; validates REPO_PATH
│   ├── state.py                  # LangGraph PipelineState TypedDict + Pydantic sub-models
│   ├── graph.py                  # LangGraph graph definition and node wiring
│   ├── main.py                   # CLI entry point (argparse + Rich)
│   │
│   ├── agents/
│   │   ├── topic_parser.py       # Phase 1: Enriches concept into structured fact sheet
│   │   ├── code_researcher.py    # Phase 1: Searches codebase, builds code evidence pack
│   │   ├── doc_analyzer.py       # Phase 2: Extracts narrative from README/bugs/arch docs
│   │   ├── concept_mapper.py     # Phase 2: Generalizes repo-specific impl to portable pattern
│   │   ├── pedagogy_planner.py   # Phase 2: Decides teaching structure and diagram types
│   │   ├── writer.py             # Phase 2: Produces guide.html from template + evidence
│   │   ├── linkedin_writer.py    # Phase 3: LinkedIn post
│   │   ├── reel_writer.py        # Phase 3: 60-second reel script
│   │   ├── diagram_generator.py  # Phase 3: Inline SVG from DiagramSpec
│   │   ├── tech_reviewer.py      # Phase 4: Verifies every factual claim vs codebase
│   │   ├── editor.py             # Phase 4: Clarity, tone, and repetition pass
│   │   └── prompts/              # System prompts as .txt files — iterate without code changes
│   │
│   ├── tools/
│   │   ├── code_search.py        # ripgrep wrapper: search_term, find_tests, list_files
│   │   ├── file_reader.py        # Extract functions/classes by name; find doc files
│   │   └── repo_manifest.py      # Directory tree + file stats for context injection
│   │
│   ├── utils/
│   │   ├── llm.py                # Unified call_llm(provider, model, ...) for Claude + OpenAI
│   │   ├── markdown_parser.py    # Parse peer_learning_concepts.md → ConceptRecord list
│   │   └── svg_builder.py        # Programmatic SVG helpers (SVGCanvas, create_state_machine)
│   │
│   └── templates/
│       ├── guide_template.html   # Gold standard HTML template — CSS never changes
│       ├── linkedin_template.md  # LinkedIn post structure with worked example
│       └── reel_template.md      # Reel script structure with scene type reference
│
├── output/
│   └── teaching_guides/
│       └── {topic-slug}/         # One directory per concept
│           ├── fact_sheet.json   # Phase 1: structured research evidence
│           ├── guide.html        # Phase 2: full teaching guide
│           ├── linkedin.md       # Phase 3
│           ├── reel_script.md    # Phase 3
│           ├── diagrams/         # Phase 3: standalone SVG/Mermaid files
│           └── metadata.json     # Difficulty, prerequisites, tags
│
├── logs/
│   └── test_YYYYMMDD_HHMMSS.log  # One per test run (gitignored)
│
└── tests/
    ├── test_markdown_parser.py   # 14 tests — no external dependencies
    ├── test_code_search.py       # 14 tests — rg-dependent tests skip without ripgrep
    ├── test_graph_flow.py        # LangGraph state transition tests (LLM calls mocked)
    └── fixtures/
        ├── sample_concepts.md    # Minimal backlog for parser tests
        └── sample_repo/          # Circuit breaker impl + tests for code search tests
```

---

## Design principles

**1. Fact sheet before writing.** The research phase produces a structured evidence pack. The writer agent never invents — it only synthesises from evidence collected in `fact_sheet.json`. This is the most important architectural decision.

**2. The template is sacred.** `src/templates/guide_template.html` defines all CSS, typography, and layout. It never changes. Only content placeholders get filled. A CSS fix applied once propagates to all 80+ guides retroactively.

**3. Diagrams are data-driven.** The diagram agent receives a structured `DiagramSpec` (nodes, edges, colors, type) rather than a prose description. This makes SVG output predictable and consistent.

**4. The review agent has repo access.** It doesn't trust the writer — it independently verifies every code reference, function name, and behavioural claim against the actual codebase before a guide is marked complete.

**5. Human edits are first-class.** Revision instructions in `--interactive` mode flow through the full planning → writing → review loop, not a lightweight patch.

**6. Resumability.** State is saved to `fact_sheet.json` after each phase. If a batch run crashes at concept 37, `--resume` picks up from where it left off.

**7. Cost awareness.** `--dry-run` shows exactly what would be processed before any API calls are made. Each concept uses approximately 15,000–25,000 input tokens and 8,000–12,000 output tokens across all agents.

---

## Development phases

| Phase | Status | Goal |
|---|---|---|
| **Phase 1 — Foundation** | ✅ Complete | Parse concepts, search codebase, produce JSON fact sheets |
| **Phase 2 — Core pipeline** | 🔲 Next | End-to-end graph producing `guide.html` for one concept |
| **Phase 3 — Content variants** | 🔲 Planned | LinkedIn posts, reel scripts, diagram generation |
| **Phase 4 — Quality gate** | 🔲 Planned | Tech review, editor, human-in-the-loop revision loop |
| **Phase 5 — Scale** | 🔲 Planned | Batch all 80+ concepts, index page, cost tracking |

---

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | — | Anthropic API key |
| `OPENAI_API_KEY` | No | — | OpenAI API key (required for concept mapper) |
| `REPO_PATH` | Yes | — | Absolute path to the codebase to analyse |
| `OUTPUT_PATH` | No | `./output/teaching_guides` | Where to write content bundles |
| `DEFAULT_WRITER_MODEL` | No | `claude-sonnet-4-6` | Model used by the writer agent |
| `DEFAULT_RESEARCH_MODEL` | No | `claude-sonnet-4-6` | Model used by research agents |
| `DEFAULT_OPENAI_MODEL` | No | `gpt-4o` | OpenAI model for concept mapper |
| `BATCH_SIZE` | No | `3` | Concepts to process in parallel during batch mode |
| `MAX_REVISIONS` | No | `2` | Max writer → reviewer → editor loops per concept |
| `LOG_LEVEL` | No | `INFO` | Application log level |

---

## Contributing

1. Run `ruff check src/ tests/` before committing
2. New agents go in `src/agents/` with a corresponding system prompt in `src/agents/prompts/`
3. System prompts are plain `.txt` files — iterate on them without touching Python code
4. All new agent nodes must have at least one mocked unit test in `tests/test_graph_flow.py`
5. The HTML template CSS is frozen — content placeholder changes only
