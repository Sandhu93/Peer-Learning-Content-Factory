# Bug Log

Bugs are recorded in the order they were discovered. Each entry answers five questions: what broke, how we found it, what it affected, what the fix was, and how we confirmed the fix held.

---

## BUG-001 — Missing `pydantic-settings` dependency

**Date:** 2026-03-27
**Severity:** High — blocked all imports of `src/config.py`
**Phase:** Phase 1 Foundation

### What broke
`src/config.py` uses `pydantic_settings.BaseSettings` for type-safe environment variable loading. The initial `pyproject.toml` included `pydantic` but not `pydantic-settings`, which is a separate package in Pydantic v2.

### How we identified it
Caught during dependency review after writing `config.py`. A runtime import of the module would have raised:
```
ModuleNotFoundError: No module named 'pydantic_settings'
```

### Impact
Any code importing `from src.config import settings` — which includes every agent and tool module — would fail at import time. The entire pipeline was un-runnable.

### Root cause
In Pydantic v2, `BaseSettings` was split out of the core `pydantic` package into a standalone `pydantic-settings` package. Code written assuming Pydantic v1's bundled settings support breaks silently until the import is attempted.

### Fix
Added `pydantic-settings>=2.0` to the `dependencies` list in `pyproject.toml` alongside `anthropic>=0.40` and `openai>=1.50`.

**File changed:** `pyproject.toml`

### Validation
```bash
pip install -e ".[dev]"
python -c "from src.config import settings; print('OK')"
```
Import succeeds without error after reinstalling.

---

## BUG-002 — `list_files` returns empty list when ripgrep is not installed

**Date:** 2026-03-27
**Severity:** Medium — silently swallowed; downstream code received empty file list
**Phase:** Phase 1 Foundation

### What broke
`list_files()` in `src/tools/code_search.py` uses ripgrep (`rg`) to enumerate files. When `rg` is not on PATH, `subprocess.run` raises `FileNotFoundError`. The function caught this exception and returned `[]` silently, giving callers no indication that the result was incomplete.

Test `TestListFiles::test_lists_python_files` asserted `len(files) > 0` and failed.

### How we identified it
First pytest run on a machine without ripgrep installed:
```
FAILED tests/test_code_search.py::TestListFiles::test_lists_python_files
AssertionError: assert 0 > 0
```

### Impact
Any code path that called `list_files()` on a machine without ripgrep would get an empty list and proceed as if the repo had no files. No error would be logged. The `code_researcher` agent would produce an evidence pack with zero evidence.

### Root cause
The function was ripgrep-only. The `FileNotFoundError` catch was intended as a safety net but silently discarded the entire result rather than falling back to an alternative.

### Fix
Added a pure-Python fallback using `Path.rglob()` that activates when `rg` is not available. Also added a `_rg_available()` helper using `shutil.which("rg")` to determine which path to take.

**File changed:** `src/tools/code_search.py`

```python
def _rg_available() -> bool:
    import shutil
    return shutil.which("rg") is not None
```

The fallback respects the same `max_files` cap and skips the same directories (`.git`, `__pycache__`, `.venv`, etc.).

### Validation
```bash
# With rg installed — uses rg path
pytest tests/test_code_search.py::TestListFiles -v

# Without rg — uses Python fallback
# (rename rg.exe temporarily or test in a clean environment)
python -c "from src.tools.code_search import list_files; print(list_files(max_files=5))"
```
Both paths return a non-empty list of `.py` files from the fixture repo.

---

## BUG-003 — ripgrep `--glob` does not accept comma-separated patterns in a single flag

**Date:** 2026-03-27
**Severity:** High — all codebase searches returned zero results
**Phase:** Phase 1 Foundation

### What broke
All three search functions (`search_term`, `search_pattern`, `find_tests`) passed a comma-separated string as a single `--glob` argument to ripgrep:
```bash
rg --glob "*.py,*.ts,*.js,..." <term> <path>
```
ripgrep treats the entire string `*.py,*.ts,*.js,...` as a single glob pattern. No source file has a name matching that literal pattern, so every search returned zero matches.

### How we identified it
Second pytest run (after ripgrep was installed). Tests in `TestSearchTerm` that had been skipping (because rg was missing) now ran. Tests that asserted `len(results) > 0` failed:
```
FAILED tests/test_code_search.py::TestSearchTerm::test_finds_class_name
assert 0 > 0
```
Tests that iterated over results vacuously passed (the `for r in results` loop body never executed on an empty list), which masked the problem initially.

### Impact
- `code_researcher` agent would find zero code evidence for any concept
- The entire research phase output would be empty, causing downstream agents (writer, reviewer) to work with no grounding evidence

### Root cause
ripgrep's `--glob` flag accepts exactly one pattern per invocation. Multiple patterns require multiple `--glob` flags:
```bash
# Wrong
rg --glob "*.py,*.ts" term path

# Correct
rg --glob "*.py" --glob "*.ts" term path
```
The comma-separated format is valid in some other tools (e.g., `fd`) but not in ripgrep.

### Fix
Added `_glob_args(glob_str: str) -> list[str]` helper that splits on commas and emits one `--glob` flag pair per pattern:
```python
def _glob_args(glob_str: str) -> list[str]:
    args = []
    for pat in glob_str.split(","):
        pat = pat.strip()
        if pat:
            args.extend(["--glob", pat])
    return args
```
All three call sites updated to use `*_glob_args(...)` instead of `"--glob", glob_str`.

**File changed:** `src/tools/code_search.py`

### Validation
```bash
pytest tests/test_code_search.py::TestSearchTerm -v
# All 5 tests pass
pytest tests/test_code_search.py::TestFindTests -v
# Both tests pass
```
Manual spot check:
```python
from src.tools.code_search import search_term
from pathlib import Path
results = search_term("CircuitBreaker", Path("tests/fixtures/sample_repo"))
assert len(results) > 0  # passes
```

---

## BUG-004 — `pytest_sessionfinish` hook crashed with `TypeError: 'int' object is not iterable`

**Date:** 2026-03-27
**Severity:** Medium — every test run exited with an error in teardown despite tests passing
**Phase:** Phase 1 Foundation

### What broke
The `pytest_sessionfinish` hook in `conftest.py` attempted to compute a pass count by iterating over `session.testscollected`:
```python
passed = sum(1 for r in session.testscollected if ...)
```
`session.testscollected` is an `int` (the count of collected items), not an iterable of test results.

### How we identified it
Running pytest produced a traceback in the teardown phase:
```
TypeError: 'int' object is not iterable
  File "conftest.py", line 80, in pytest_sessionfinish
    passed = sum(1 for r in session.testscollected if ...)
```
The test results themselves were correct — only the session summary logging failed.

### Impact
Every test run printed a stack trace at the end. CI output would appear broken even when all tests passed. The log file was still written correctly, but the session finish log line was missing.

### Root cause
Incorrect assumption about the `pytest.Session` API. `session.testscollected` counts items; individual results are only available inside `pytest_runtest_logreport`, which fires per-test.

### Fix
Removed the pass-count calculation from `pytest_sessionfinish`. The per-test result logging in `pytest_runtest_logreport` already captures every outcome individually. The session finish line logs exit code and collection count, which is sufficient.

**File changed:** `conftest.py`

### Validation
```bash
pytest tests/test_markdown_parser.py
# No traceback at the end
# Final line: "28 passed in 0.64s"
# Log file ends with: "Session finished — exit code 0 | collected 28 items"
```
