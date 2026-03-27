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

The `tech_reviewer` agent (Phase 3) independently verifies every factual claim in the generated guide against the actual codebase, providing a second line of defence.

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

## ADR-010 — Parallel LangGraph nodes must return only their own keys (no `**state` spread)

### Date
2026-03-27

### Status
Accepted

### Context
LangGraph uses `LastValue` channels for state keys by default. When two parallel branches both execute in the same graph step, LangGraph collects their return dicts and merges them via `apply_writes`. If both dicts contain the same key — even with the same value — `LastValue.update()` raises `InvalidUpdateError: Can receive only one value per step`.

`code_researcher` and `doc_analyzer` both previously returned `{**state, "their_key": value}`. This passed every key in `PipelineState` through both nodes. At fan-in, LangGraph saw two writes to `concept_name`, `category`, `repo_path`, etc., and crashed.

### Decision
Any node that runs as part of a parallel branch (fan-out → fan-in) **must return only the keys it is responsible for writing**. It must not include `**state` or any key owned by a sibling branch.

Sequential nodes (those that run alone in their step) may return `{**state, "new_key": value}`, but returning only owned keys is safer and is the preferred pattern going forward.

### Rule (enforceable in tests)
> A parallel node's return dict must be disjoint from all sibling nodes' return dicts and must not contain any key from `PipelineState` that the node does not write as part of its defined responsibility.

### Consequences
- **Positive:** Eliminates the entire class of `InvalidUpdateError` fan-in crashes.
- **Positive:** Makes each node's output contract explicit and auditable.
- **Negative:** Node return values no longer represent the full state snapshot — callers (tests) must merge with `{**base_state, **result}` to simulate what LangGraph produces after fan-in.
- **Watch:** Any new parallel branch added in future phases must follow this rule. The `TestParallelBranchIsolation` test class is the living enforcement of this contract.

---

## ADR-011 — Editor uses patch-based diffs, not full HTML re-generation

**Date:** 2026-03-27
**Status:** Accepted

### Context
The `editor` agent's job is to apply corrections from `tech_reviewer` and polish prose. The guide HTML is 40–50k characters. Two approaches were considered:

| Option | Assessment |
|---|---|
| **Editor outputs full HTML** | Simple prompt; but Claude rewriting 40k chars of HTML is expensive, slow, and risks structural drift — broken tags, altered CSS classes, missing placeholders |
| **Editor outputs {original_text → replacement_text} patches** | Cheaper, faster, structurally safe; only the specific passages change |

### Decision
The editor's LLM call returns a JSON object with a `changes` array: each item is `{original: "...", replacement: "..."}`. The node applies these as verbatim string replacements to the existing `guide_html` in Python. If an `original` string is not found in the HTML (e.g., the LLM hallucinated the passage), the change is skipped and a warning is logged — the guide is not corrupted.

### Consequences
- **Positive:** HTML structure is preserved. CSS classes, template slots, and SVG elements are untouched.
- **Positive:** Token cost is ~10x lower than re-generating full HTML.
- **Negative:** The LLM must quote passages verbatim from the HTML — any paraphrase or reconstruction causes the replacement to silently fail. Prompt emphasises "must be a verbatim substring".
- **Watch:** If a `changes` entry quotes a passage that appears multiple times in the HTML, only the first occurrence is replaced (`str.replace(..., 1)`). The editor prompt limits changes to passages long enough (≥30 chars) to be unique.

---

## ADR-012 — File writing moved from `main.py` into a `save_outputs` graph node

**Date:** 2026-03-27
**Status:** Accepted

### Context
In Phase 2, `run_single_concept()` in `main.py` wrote all output files inline after `graph.ainvoke()` returned. This worked, but it had two problems:
1. The human-in-the-loop interrupt (Phase 3) should pause *before* files are written — not after. If files were written before the human approved, the pause would be pointless.
2. File writing outside the graph meant the graph's output could not be cleanly tested end-to-end (the final artefacts were not part of the graph's observable state).

### Decision
A `save_outputs` node is added as the final graph node. It reads `output_path` from state (set in `initial_state` before the run), writes all files, and sets `is_complete: True`. `main.py` only prints a summary after the graph completes — it no longer contains file I/O.

`output_path` is added to `initial_state` in `run_single_concept()` before `ainvoke()` is called:
```python
"output_path": str(out_root)
```

In `--interactive` mode, `interrupt_before=["save_outputs"]` causes LangGraph to pause before the node runs, allowing human review before any files land on disk.

### Consequences
- **Positive:** Human-in-the-loop interrupt fires before files are written. Aborting leaves no partial output.
- **Positive:** The complete pipeline — including file writing — is exercised by a single graph run.
- **Negative:** `output_path` must be in `initial_state`. A caller that forgets to set it will cause `save_outputs` to log an error and set `is_complete: False` rather than crashing the graph.
- **Watch:** `save_outputs` uses `encoding="utf-8"` on every `write_text()` call (see BUG-006, BUG-008 pattern).

---

## ADR-013 — Phase 4 content variant fan-out: writer produces guide_html only; dedicated agents own standalone outputs

**Date:** 2026-03-28
**Status:** Accepted

### Context
In Phase 3, `writer` produced all four content outputs: `guide_html`, `linkedin_post`, `reel_script`, and `diagram_svgs`. This made the writer prompt enormous and spread responsibility too thin — LinkedIn copy, reel scripting, and SVG rendering have distinct quality criteria that compete inside a single LLM call.

Phase 4 goal: higher-quality standalone variants by giving each output its own dedicated agent with a focused prompt and (where appropriate) a different model.

### Options considered

| Option | Pros | Cons |
|---|---|---|
| **Keep writer producing everything; add dedicated agents that post-process** | No graph changes | Duplicates work; post-processing agents would overwrite writer's fields |
| **Strip linkedin/reel/diagram from writer; dedicated agents produce them from scratch** | Clear ownership; no duplication | Dedicated agents lose the guide context unless guide_html is passed to them |
| **Writer produces guide_html; dedicated agents read guide_html for context** | Clean ownership split; agents get rich context from the finished guide; no duplication | Diagram SVGs embedded in guide_html are re-rendered by writer for the template; diagram_generator provides the standalone list |

### Decision
`writer` produces `guide_html` only. The three dedicated agents fan out in parallel after writer:
- `linkedin_writer` — reads `guide_html` + `teaching_plan`; produces `linkedin_post`
- `reel_writer` — reads `guide_html` + `teaching_plan`; produces `reel_script` (GPT-4o → Claude fallback)
- `diagram_generator` — reads `diagram_specs`; produces `diagram_svgs` (pure Python, no LLM)

`tech_reviewer` is the fan-in point — it waits for all three to complete before running.

The guide HTML still contains embedded linkedin/reel content (writer's LLM call still generates these for the HTML template). The dedicated agents produce *better* standalone variants for the separate `.md` files. This is intentional duplication: the HTML guide is self-contained; the standalone files are optimised for their respective distribution channels.

### Consequences
- **Positive:** Each agent has a focused prompt tuned to its output format.
- **Positive:** `reel_writer` can use GPT-4o (which was planned for this role in the original phase roadmap) without making the entire guide generation dependent on OpenAI availability.
- **Positive:** `diagram_generator` has no LLM cost — pure `svg_builder` call, always fast.
- **Negative:** Writer's LLM call still generates linkedin/reel content for the HTML template, so there is some token duplication. Acceptable at Phase 4 scale; revisit if cost becomes significant.
- **Watch:** All three parallel agents must follow ADR-010 (return only owned keys) to avoid write conflicts during LangGraph state merging.
