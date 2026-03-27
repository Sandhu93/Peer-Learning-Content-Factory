# Architecture Decision Records

This file records significant decisions made during the design and development of this project: what was chosen, what was considered and rejected, and why. The reasoning matters as much as the decision — especially when revisiting a choice after six months.

Format: decision title, date, status, context, options considered, the choice, and the consequences.

---

## ADR-001 — Use LangGraph for agent orchestration

**Date:** 2026-03-27
**Status:** Accepted

### Context
The pipeline has multiple agents that need to run in sequence, some in parallel, with conditional routing (the reviewer can send the writer back to revise). There is also a human-in-the-loop requirement. We needed a framework to manage state, routing, and concurrency without building it from scratch.

### Options considered

| Option | Pros | Cons |
|---|---|---|
| **LangGraph** | Explicit graph model, first-class state management, built-in human-in-the-loop, active development | Younger library, API is still evolving |
| **Plain asyncio** | No dependencies, full control | State management, error recovery, and conditional routing all hand-rolled — high implementation cost |
| **LangChain Chains/Agents** | Familiar, many examples | Less explicit control over graph shape; harder to add conditional edges and human checkpoints |
| **Prefect / Airflow** | Production-grade workflow orchestration | Heavyweight, designed for data pipelines not LLM agents, adds significant operational complexity |

### Decision
LangGraph. Its graph model maps directly to the pipeline shape (fan-out to parallel nodes, conditional back-edges for revision loops, human-in-the-loop checkpoints). The explicit state TypedDict makes the data contract between agents clear and testable.

### Consequences
- **Positive:** Pipeline topology is readable as code. Adding a new Phase 2 node does not require changing existing nodes.
- **Positive:** State is typed and testable. Agent nodes can be unit-tested by passing mock state.
- **Negative:** LangGraph's API has changed across minor versions. We pin to `>=0.2` and need to test upgrades.
- **Watch:** If LangGraph's human-in-the-loop API changes significantly, `src/graph.py` will need an update.

---

## ADR-002 — Claude as primary LLM, GPT-4o as secondary for concept mapping

**Date:** 2026-03-27
**Status:** Accepted

### Context
Different agents have different strengths. The writer agent needs to produce 3,000–5,000 words of coherent, well-structured HTML. The concept mapper needs to abstract a repo-specific implementation into a portable software engineering pattern.

### Options considered

| Option | Assessment |
|---|---|
| **Claude only** | Simpler (one API, one key), but Claude's abstraction/generalisation output is slightly weaker than GPT-4o for structured taxonomies |
| **GPT-4o only** | Strong at structured output and abstraction, but Claude produces significantly better long-form prose for the teaching guide |
| **Claude primary + GPT-4o for concept mapper** | Uses each model where it is strongest |
| **Gemini** | Not evaluated — add to future comparison |

### Decision
Claude (`claude-sonnet-4-6` default, `claude-opus-4-6` for highest quality) for all writing, reviewing, and code understanding tasks. GPT-4o for concept_mapper (abstraction and generalisation) and reel_writer (punchy short-form content).

This is configurable via `DEFAULT_WRITER_MODEL` and `DEFAULT_OPENAI_MODEL` in `.env` — it is not hardcoded.

### Consequences
- **Positive:** Output quality is maximised for each task type.
- **Negative:** Two API keys required. Two billing accounts to monitor.
- **Negative:** If OpenAI API is unavailable, concept_mapper and reel_writer fail. Mitigation: add fallback routing to Claude in Phase 4.
- **Watch:** Model capabilities change with each release. Re-evaluate routing quarterly.

---

## ADR-003 — Ripgrep for codebase search, with pure-Python fallback

**Date:** 2026-03-27
**Status:** Accepted

### Context
The code_researcher agent needs to search a large codebase (potentially 100k+ lines) for specific identifiers, class names, and patterns. The search needs to be fast and support regex.

### Options considered

| Option | Pros | Cons |
|---|---|---|
| **ripgrep (`rg`)** | Extremely fast, regex support, JSON output mode, ignores `.gitignore` and `.git` automatically | External binary dependency, not available everywhere by default |
| **Python `grep` via subprocess** | No binary dependency | Much slower on large repos, no JSON output, more fragile argument handling |
| **Python `re` module with manual file walking** | No dependency | Slow, no automatic `.gitignore` support |
| **`ast.walk` + `re` on parsed files** | Semantically precise for Python | Only works for Python, not TypeScript/Go/etc. |

### Decision
ripgrep as primary. Pure-Python `Path.rglob()` fallback for `list_files()` when `rg` is not available. For search functions (`search_term`, `find_tests`), raise a `RuntimeError` if ripgrep is absent — these are core to the pipeline and a silent empty result would produce wrong output.

Tests that require ripgrep are marked `@needs_rg` and skip automatically in environments where it's not installed.

### Consequences
- **Positive:** Search is fast enough to run multiple queries per concept without noticeable delay.
- **Positive:** JSON output mode (`rg --json`) gives structured, unambiguous results.
- **Negative:** Requires `rg` to be installed. Added to README prerequisites.
- **Lesson learned (BUG-003):** ripgrep's `--glob` flag does not accept comma-separated patterns. Multiple patterns require multiple `--glob` flags. Added `_glob_args()` helper to handle this.

---

## ADR-004 — HTML template is frozen; writer fills content placeholders only

**Date:** 2026-03-27
**Status:** Accepted

### Context
The system will generate 80+ guides. If each guide is a fully custom HTML document, visual consistency requires the writer to reproduce the same CSS and layout every time — which it will not do reliably. Small differences in color, spacing, or typography accumulate into an inconsistent library.

### Options considered

| Option | Assessment |
|---|---|
| **Writer generates full HTML** | Maximum flexibility; inconsistency guaranteed across 80+ runs |
| **Post-processing with CSS injection** | Fragile; depends on HTML structure being predictable |
| **Fixed template with content placeholders** | Writer only fills `{{concept_name}}`, `{{guide_html}}`, etc. CSS is untouched |
| **Jinja2 template rendering** | More powerful than plain placeholder replacement; allows conditionals and loops in the template |

### Decision
Fixed template (`src/templates/guide_template.html`) with Jinja2-style placeholder substitution. The CSS, typography, color system, and layout are defined once in the template and never modified by any agent. The writer receives the template in its system prompt and produces only the content for each placeholder.

This template is the **gold standard** — all visual quality decisions are made here, not in any agent prompt.

### Consequences
- **Positive:** Every guide looks identical regardless of which model or temperature was used to write it.
- **Positive:** A single CSS fix (e.g., adjusting dark mode contrast) propagates to all 80+ guides retroactively — just regenerate from the existing fact sheets.
- **Negative:** Adding a new section type (e.g., a quiz block) requires updating the template, then regenerating guides that should include it.
- **Negative:** The writer's output must match the template structure exactly. Prompt engineering is required to ensure this.

---

## ADR-005 — Fact sheet is the single source of truth; writer never invents

**Date:** 2026-03-27
**Status:** Accepted

### Context
LLM hallucination is a genuine risk in a content-generation pipeline. A writer agent that invents code examples, file paths, or function names that don't exist in the repo produces guides that are confidently wrong — which is worse than incomplete.

### Decision
The research phase (topic_parser + code_researcher + doc_analyzer) runs before any writing. It produces a `fact_sheet.json` with verified code snippets, file paths, and doc context. The writer agent receives only content from this fact sheet — it is not permitted to add code examples or factual claims that aren't in the fact sheet.

The `tech_reviewer` agent (Phase 4) independently verifies every factual claim in the generated guide against the actual codebase, providing a second line of defence.

### Consequences
- **Positive:** Guides are grounded in the actual codebase. Function names, file paths, and code behaviour descriptions are accurate.
- **Positive:** Separating research from writing makes each phase independently testable and improvable.
- **Negative:** The research phase must be comprehensive. If code_researcher misses an important file, the writer has nothing to draw from for that aspect of the concept.
- **Watch:** The writer's system prompt must explicitly state "only use content from the fact sheet". This constraint needs to be reinforced in prompt revisions.

---

## ADR-006 — State persistence to JSON after each phase

**Date:** 2026-03-27
**Status:** Accepted

### Context
Processing 80+ concepts with a multi-phase pipeline creates a real risk of partial failure. If the process crashes at concept 40 in Phase 3, should it restart from scratch?

### Decision
After each phase completes, the state is serialised to `fact_sheet.json` (and later to phase-specific files). The `--resume` flag reads existing outputs and skips concepts/phases that are already complete.

### Consequences
- **Positive:** A crash at any point loses at most one concept's current phase of work.
- **Positive:** Resuming is cheap — no re-running of expensive LLM research for completed concepts.
- **Negative:** JSON serialisation of `PipelineState` requires that all values are JSON-serialisable. Pydantic models must be converted with `.model_dump()` before storage.
- **Watch:** If the state schema changes between runs (e.g., a new field is added), existing JSON files may be missing that field. Use `.get()` with defaults when reading persisted state.
