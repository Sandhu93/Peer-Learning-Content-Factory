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

---

## ADR-007 — `repo_path` is a per-run `PipelineState` field, not a global setting

**Date:** 2026-03-27
**Status:** Accepted

### Context
Initially `REPO_PATH` was stored in `Settings` with a default of `Path(".")`. This caused BUG-005: when the env var was not set, agents silently searched the content factory's own source tree instead of the target codebase. Additionally, the existence check ran at import time, crashing the entire app on environments where the path didn't yet exist — even for commands like `--list` that don't need a repo at all.

The deeper issue: `repo_path` is a **run input** — it can legitimately differ between invocations. A CLI user might pass `--repo` to override. A future web frontend will receive a different path per user request. Global singletons cannot represent per-request variation.

### Options considered

| Option | Assessment |
|---|---|
| **Keep in `Settings`, add `--repo` to mutate it** | Mutating a module-level singleton is an anti-pattern; breaks concurrent requests |
| **Validate at import time with a required env var** | Forces every environment to have `REPO_PATH`, even tests and `--list` which don't need it |
| **Optional in `Settings`, resolved at run time, stored in state** | Clean separation: config holds the default, state holds the resolved value for this run |

### Decision
`repo_path` is `Optional[Path] = None` in `Settings`. A new `effective_repo_path(override)` method resolves the value at the point of use — checking the CLI override first, then the `.env` default, then raising a `ValueError` with a three-option error message if neither is configured.

The resolved path is placed in `PipelineState["repo_path"]` as a `str` at the start of each run. Every agent that needs the path reads it from state, not from `settings`. This means:
- Two concurrent API requests can target different repos without race conditions.
- `--list` and other commands that don't invoke the graph never trigger the path check.
- Adding a frontend only requires placing `request.body.repo_path` in the initial state — no other code changes.

### Consequences
- **Positive:** `--list`, `--batch --dry-run`, and test runs that don't need a repo never crash due to a missing path.
- **Positive:** The pattern generalises cleanly to any per-run input (language filter, output dir override, etc.).
- **Negative:** Agents must remember to read from `state["repo_path"]` rather than `settings.repo_path`. A new agent that forgets this will silently use the wrong path if `REPO_PATH` is not set. Mitigated by the fallback `state.get("repo_path") or settings.repo_path` guard in `code_researcher`.
- **Watch:** When the frontend is added, validate `repo_path` from the request body the same way as `--repo` — through `effective_repo_path()` — before passing it to the graph. Do not bypass the validation step.

---

## ADR-008 — `doc_context` and `implementation_notes` are separate state fields for parallel safety

**Date:** 2026-03-27
**Status:** Accepted

### Context
Phase 2 added `doc_analyzer` running in parallel with `code_researcher`. Both agents need to contribute different types of context to later nodes. The original design had `code_researcher` writing `implementation_summary` and `evidence_gaps` into `doc_context`. This was fine in Phase 1 (sequential). In Phase 2, if both parallel branches write to the same `doc_context` key, LangGraph's state merge applies one branch's update on top of the other — the second branch to complete silently overwrites the first's contribution.

### Decision
Split the two agents' outputs into distinct top-level state keys:
- `code_researcher` → writes `code_evidence` + `implementation_notes` (`{implementation_summary, evidence_gaps}`)
- `doc_analyzer` → writes `doc_context` (`{feature_rationale, bug_stories[], tradeoffs[], evolution_notes}`)

No key is touched by both parallel branches. `concept_mapper` reads from both after the fan-in.

### Consequences
- **Positive:** No parallel write conflicts. State merge is safe and deterministic.
- **Positive:** Each field's ownership is explicit — `implementation_notes` always comes from code analysis, `doc_context` always comes from human-written documentation.
- **Negative:** Downstream agents must read from two separate keys (`implementation_notes` and `doc_context`) instead of one.
- **Watch:** If a future agent needs to write the same key as a parallel sibling, either split the key again or add a dedicated merge node between the parallel branches and the fan-in point.

---

## ADR-009 — Writer agent handles diagram rendering inline (no separate diagram_generator yet)

**Date:** 2026-03-27
**Status:** Accepted

### Context
The full pipeline design includes a dedicated `diagram_generator` agent in Phase 4. Phase 2 needed diagrams in the output to make guides usable, but building a dedicated agent was scope-creep for the current phase.

### Decision
`writer.py` renders diagrams synchronously in Python using `svg_builder` before calling the LLM for content. `pedagogy_planner` produces `diagram_specs` in a format directly compatible with `create_state_machine()`. The writer substitutes the rendered SVG strings into the template alongside the LLM-generated content.

### Consequences
- **Positive:** guides.html has working inline SVG diagrams from Phase 2 onward.
- **Positive:** No extra LLM call needed for diagram generation — the spec-to-SVG conversion is pure Python.
- **Negative:** Diagram quality is limited to what `svg_builder`'s node/edge spec can express. Complex architecture diagrams with curved arrows or layered layouts aren't supported yet.
- **Watch:** When Phase 4 adds `diagram_generator`, it should replace the inline rendering in `writer.py` rather than duplicate it.
