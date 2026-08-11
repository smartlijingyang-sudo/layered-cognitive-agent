# Code Execution Artifact Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the code execution artifact pipeline so generated files (PDF, images, etc.) are automatically harvested from the sandbox and surfaced to the frontend.

**Architecture:** Five minimal changes across 4 files: (1) unify artifact harvesting in `parse_terminal_response()`, (2) inject ADR-0046-compliant scanner bootstrap in `execute_code()`, (3) pipe `generated_files` through `ComputerOpResult` → `build_computer_observation()` → `Observation.extra["files"]`, (4) add PDF to previewable MIME types. Reuses existing `_stored_part()` and workspace artifact ledger.

**Tech Stack:** Python 3.11, pytest, dataclasses, `strip_artifacts()` from `onlyboxes_artifacts.py`

**Spec:** `docs/superpowers/specs/2026-08-11-code-execution-artifact-pipeline-design.md`

## Global Constraints

- ADR-0046: artifact scanner must only scan `/mnt/data/outputs/` (`SANDBOX_OUTPUT_SUBDIR`), never `/mnt/data/` root
- Reuse `_stored_part()` from `sandbox_observation.py` — do not duplicate FileStore logic
- `build_computer_observation()` must record to workspace artifact ledger (align with `build_exec_observation()`)
- All public functions need type annotations
- `uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run pytest` must pass

---

### Task 1: Fix `parse_terminal_response()` — add `strip_artifacts()`

**Files:**
- Modify: `lca/layer0_infra/sandbox/onlyboxes_bootstrap.py:168-215`
- Test: `tests/test_onlyboxes_sandbox.py`

**Interfaces:**
- Consumes: `strip_artifacts()` from `onlyboxes_artifacts.py` (already imported in this file)
- Produces: `parse_terminal_response()` returns `SandboxResult` with `generated_files` populated when stdout contains artifact markers

- [ ] **Step 1: Write failing test — `parse_terminal_response` harvests artifacts**

Add to `tests/test_onlyboxes_sandbox.py`, inside the `StripArtifactsTests` class or a new `ParseTerminalResponseTests` class:

```python
class ParseTerminalResponseHarvestTests(unittest.TestCase):
    """parse_terminal_response() should call strip_artifacts() — ADR-0046 alignment."""

    def _make_response(self, stdout: str, exit_code: int = 0) -> MagicMock:
        resp = MagicMock()
        resp.status_code = 200
        resp.text = json.dumps({"exit_code": exit_code, "stdout": stdout, "stderr": ""})
        resp.ok = True
        return resp

    def test_harvests_artifact_block_from_stdout(self) -> None:
        from lca.layer0_infra.sandbox.onlyboxes_bootstrap import parse_terminal_response
        from lca.layer0_infra.sandbox.streaming import SandboxStreamEmitter

        stdout = "result: 42\n" + _artifact_block([("report.pdf", b"%PDF-1.4...")])
        emitter = SandboxStreamEmitter("inv_test")
        result = parse_terminal_response(self._make_response(stdout), emitter)

        self.assertTrue(result.success)
        self.assertEqual(len(result.generated_files), 1)
        self.assertEqual(result.generated_files[0].name, "report.pdf")
        self.assertEqual(result.generated_files[0].data, b"%PDF-1.4...")
        # stdout should be cleaned (artifact block removed)
        self.assertIn("result: 42", result.stdout)
        self.assertNotIn(ARTIFACT_BEGIN, result.stdout)

    def test_no_artifact_block_is_safe_noop(self) -> None:
        from lca.layer0_infra.sandbox.onlyboxes_bootstrap import parse_terminal_response
        from lca.layer0_infra.sandbox.streaming import SandboxStreamEmitter

        emitter = SandboxStreamEmitter("inv_test")
        result = parse_terminal_response(self._make_response("hello world\n"), emitter)

        self.assertTrue(result.success)
        self.assertEqual(result.generated_files, ())
        self.assertEqual(result.stdout, "hello world\n")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_onlyboxes_sandbox.py::ParseTerminalResponseHarvestTests -v`
Expected: FAIL — `generated_files` is empty tuple (current `parse_terminal_response` doesn't call `strip_artifacts`)

- [ ] **Step 3: Fix `parse_terminal_response()`**

In `lca/layer0_infra/sandbox/onlyboxes_bootstrap.py`, modify `parse_terminal_response()`:

```python
def parse_terminal_response(
    response: httpx.Response,
    emitter: SandboxStreamEmitter,
) -> SandboxResult:
    # ... existing JSON parsing and status code checks unchanged ...

    stdout = str(payload.get("stdout") or "")
    stderr = str(payload.get("stderr") or "")

    # ADR-0046 alignment: harvest artifact block (same as parse_exec_response)
    cleaned_stdout, generated, diags = strip_artifacts(stdout)
    if diags:
        stderr = stderr + "".join(diags)

    if cleaned_stdout:
        emitter.emit_stdout(cleaned_stdout)
    if stderr:
        emitter.emit_stderr(stderr)

    success = exit_code == 0
    error_text = "" if success else (stderr.strip() or f"exit_code={exit_code}")
    return SandboxResult(
        stdout=cleaned_stdout,  # was: stdout
        stderr=stderr,
        exit_code=exit_code,
        success=success,
        error=error_text,
        generated_files=tuple(generated),  # new
    )
```

The `strip_artifacts` import already exists at the top of the file (used by `parse_exec_response`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_onlyboxes_sandbox.py::ParseTerminalResponseHarvestTests -v`
Expected: PASS

- [ ] **Step 5: Run full sandbox test suite to verify no regressions**

Run: `uv run pytest tests/test_onlyboxes_sandbox.py -v`
Expected: All PASS (including existing `StripArtifactsTests`, `OnlyboxesAdapterTests`)

- [ ] **Step 6: Commit**

```bash
git add lca/layer0_infra/sandbox/onlyboxes_bootstrap.py tests/test_onlyboxes_sandbox.py
git commit -m "fix(sandbox): parse_terminal_response harvests artifacts (ADR-0046 alignment)

Unifies terminal and exec response parsing — both now call strip_artifacts().
Since all adapter paths (run, run_in_session, run_terminal) converge on
_exec_terminal() → parse_terminal_response(), this single fix covers
execute_code, run_command, and sandbox_execute."
```

---

### Task 2: `ComputerOpResult` + `build_computer_observation()` — file pipeline

**Files:**
- Modify: `lca/layer0_infra/computer/runtime.py:43-50` (ComputerOpResult dataclass)
- Modify: `lca/layer0_infra/tools/computer/observations.py` (full file, 54 lines)
- Modify: `lca/layer0_infra/tools/computer/tool_set.py:58-65` (pass `store` to observation builder)
- Test: `tests/test_computer_tools.py`

**Interfaces:**
- Consumes: `_stored_part()` from `sandbox_observation.py`, `get_run_workspace()` from `workspace/scope.py`
- Produces: `build_computer_observation(result, *, tool_name, start, store)` → `Observation` with `extra["files"]` and workspace ledger recording

- [ ] **Step 1: Write failing test — `build_computer_observation` carries files**

Add to `tests/test_computer_tools.py`:

```python
class TestBuildComputerObservationFiles(unittest.TestCase):
    """build_computer_observation should pipe generated_files into Observation.extra['files']."""

    def test_files_in_extra_when_generated(self) -> None:
        from unittest.mock import MagicMock
        from lca.contracts.models.core.sandbox import SandboxFile
        from lca.layer0_infra.computer.runtime import ComputerOpResult
        from lca.layer0_infra.tools.computer.observations import build_computer_observation
        from lca.layer0_infra.file_store import LocalFileStore
        import tempfile, os

        result = ComputerOpResult(
            success=True,
            content="output text",
            state={"output": "output text"},
            generated_files=(
                SandboxFile(name="primes.pdf", mime_type="application/pdf", data=b"%PDF-1.4"),
            ),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            store = LocalFileStore(root=os.path.join(tmpdir, "files"))
            obs = build_computer_observation(
                result, tool_name="execute_code", start=0.0, store=store
            )

        self.assertTrue(obs.success)
        files = (obs.extra or {}).get("files", [])
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["name"], "primes.pdf")
        self.assertEqual(files[0]["mimeType"], "application/pdf")
        self.assertIn("url", files[0])
        self.assertIn("attachmentId", files[0])

    def test_no_files_when_empty(self) -> None:
        from lca.layer0_infra.computer.runtime import ComputerOpResult
        from lca.layer0_infra.tools.computer.observations import build_computer_observation
        from lca.layer0_infra.file_store import LocalFileStore
        import tempfile, os

        result = ComputerOpResult(
            success=True,
            content="ok",
            state={},
            generated_files=(),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            store = LocalFileStore(root=os.path.join(tmpdir, "files"))
            obs = build_computer_observation(
                result, tool_name="execute_code", start=0.0, store=store
            )

        self.assertTrue(obs.success)
        self.assertNotIn("files", obs.extra or {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_computer_tools.py::TestBuildComputerObservationFiles -v`
Expected: FAIL — `build_computer_observation` doesn't accept `store` parameter, doesn't handle `generated_files`

- [ ] **Step 3: Add `generated_files` field to `ComputerOpResult`**

In `lca/layer0_infra/computer/runtime.py`, modify the dataclass:

```python
from lca.contracts.models.core.sandbox import (
    DEFAULT_SANDBOX_TIMEOUT_S,
    SANDBOX_MOUNT_ROOT,
    SandboxExecResult,
    SandboxFile,  # new import
)


@dataclass(frozen=True)
class ComputerOpResult:
    success: bool
    content: str
    state: dict[str, Any]
    error: str = ""
    exec_result: SandboxExecResult | None = None
    generated_files: tuple[SandboxFile, ...] = ()  # new
```

- [ ] **Step 4: Update `build_computer_observation()` to handle files**

Rewrite `lca/layer0_infra/tools/computer/observations.py`:

```python
"""Build computer use observations for journal + LobeHub wire."""

from __future__ import annotations

import time
from typing import Any

from lca.contracts.atoms.enums import ContentType
from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import FAILURE_KIND, FAILURE_KIND_EXECUTION
from lca.contracts.models.core.decision import Observation
from lca.layer0_infra.computer.runtime import ComputerOpResult
from lca.layer0_infra.file_store import FileStore
from lca.layer0_infra.tools.sandbox_observation import _stored_part
from lca.layer0_infra.workspace.scope import get_run_workspace


def build_computer_observation(
    result: ComputerOpResult,
    *,
    tool_name: str,
    start: float,
    store: FileStore,
) -> Observation:
    del tool_name
    latency_ms = int((time.monotonic() - start) * 1000)
    payload: dict[str, Any] = {
        **result.state,
        "content": result.content,
        "summary": _truncate(result.content),
    }
    if result.exec_result is not None:
        payload["exit_code"] = result.exec_result.exit_code

    # File pipeline: store generated files and record in workspace ledger
    file_parts: list[dict[str, Any]] = []
    for gen in result.generated_files:
        file_parts.append(_stored_part(store, gen.data, gen.name, gen.mime_type))

    extra: dict[str, Any] = {}
    if file_parts:
        extra["files"] = file_parts

    if not result.success:
        extra[FAILURE_KIND] = FAILURE_KIND_EXECUTION
        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=payload,
            content_type=ContentType.STRUCTURED,
            error=result.error or result.content or "computer operation failed",
            latency_ms=latency_ms,
            extra=extra,
        )

    # Record in workspace artifact ledger (aligned with build_exec_observation)
    if file_parts:
        workspace = get_run_workspace()
        if workspace is not None:
            workspace.artifacts.record_from_tool_files(
                file_parts, tool_name=tool_name, agent_role=""
            )

    return Observation(
        observation_id=new_id("obs"),
        success=True,
        payload=payload,
        content_type=ContentType.STRUCTURED,
        latency_ms=latency_ms,
        extra=extra,
    )


def _truncate(text: str, limit: int = 8000) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
```

- [ ] **Step 5: Update `tool_set.py` to pass `store`**

In `lca/layer0_infra/tools/computer/tool_set.py`, modify `_instantiate_computer_tool`:

```python
def _instantiate_computer_tool(
    spec: ComputerToolSpec,
    *,
    sandbox: Sandbox,
    store: FileStore,
) -> Tool:
    runtime = ComputerRuntime(sandbox=sandbox, store=store)

    async def execute(_self: Tool, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        result = await spec.handler(runtime, args)
        return build_computer_observation(
            result,
            tool_name=spec.name,
            start=start,
            store=store,  # pass store
        )

    # ... rest unchanged
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_computer_tools.py::TestBuildComputerObservationFiles -v`
Expected: PASS

- [ ] **Step 7: Run full computer tools test suite**

Run: `uv run pytest tests/test_computer_tools.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add lca/layer0_infra/computer/runtime.py lca/layer0_infra/tools/computer/observations.py lca/layer0_infra/tools/computer/tool_set.py tests/test_computer_tools.py
git commit -m "fix(tools): computer observation pipes generated_files to journal

- ComputerOpResult gains generated_files field (tuple[SandboxFile, ...])
- build_computer_observation() stores files via _stored_part() (reused from
  sandbox_observation.py) and records in workspace artifact ledger
- tool_set.py passes FileStore to observation builder
- Aligns computer tool path with sandbox_execute observation pipeline"
```

---

### Task 3: `execute_code()` — inject scanner + pass files + source_code

**Files:**
- Modify: `lca/layer0_infra/computer/runtime_exec.py:49-90`
- Test: `tests/test_onlyboxes_sandbox.py` (integration with InlineSandbox)

**Interfaces:**
- Consumes: `RunBoundSandboxRuntime.execute()`, `SandboxExecResult.generated_files`
- Produces: `execute_code()` returns `ComputerOpResult` with `generated_files` and `state["code"]`

- [ ] **Step 1: Write failing test — `execute_code` injects scanner and captures files**

Add to `tests/test_onlyboxes_sandbox.py`:

```python
class ExecuteCodeArtifactTests(unittest.IsolatedAsyncioTestCase):
    """execute_code() should inject artifact scanner and capture generated files."""

    async def test_scanner_injected_in_code(self) -> None:
        """The code passed to the sandbox should contain the artifact scanner."""
        from lca.layer0_infra.computer.runtime_exec import _ARTIFACT_SCANNER

        # Verify the scanner constant exists and targets /mnt/data/outputs
        self.assertIn("/mnt/data/outputs", _ARTIFACT_SCANNER)
        self.assertIn("__LCA_ONLYBOXES_ARTIFACTS__", _ARTIFACT_SCANNER)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_onlyboxes_sandbox.py::ExecuteCodeArtifactTests -v`
Expected: FAIL — `_ARTIFACT_SCANNER` doesn't exist yet

- [ ] **Step 3: Implement `_ARTIFACT_SCANNER` and inject in `execute_code()`**

In `lca/layer0_infra/computer/runtime_exec.py`:

```python
import textwrap

# ADR-0046 compliant: only scans /mnt/data/outputs/
_ARTIFACT_SCANNER = """
import os as _os, json as _json, base64 as _b64, mimetypes as _mt
try:
    _scan_files = []
    _output_dir = "/mnt/data/outputs"
    if _os.path.isdir(_output_dir):
        for _fname in _os.listdir(_output_dir):
            _fpath = _os.path.join(_output_dir, _fname)
            if _os.path.isfile(_fpath):
                try:
                    with open(_fpath, "rb") as _fh:
                        _raw = _fh.read()
                    _scan_files.append({
                        "name": _fname,
                        "b64": _b64.b64encode(_raw).decode(),
                        "mime_type": _mt.guess_type(_fname)[0] or "application/octet-stream",
                    })
                except Exception:
                    pass
    if _scan_files:
        print("__LCA_ONLYBOXES_ARTIFACTS__" + _json.dumps(_scan_files) + "__END_LCA_ARTIFACTS__")
except Exception:
    pass
"""
```

Modify `execute_code()`:

```python
async def execute_code(
    self: _GuestOpHost,
    *,
    code: str,
    language: str = "python",
    description: str = "",
    timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
) -> ComputerOpResult:
    del description
    lang = (language or "python").lower()
    runtime = await ensure_sandbox_runtime(
        self._sandbox,
        self._store,
        attachment_ids=get_current_run_attachment_ids(),
    )
    inv = get_current_tool_invocation_id() or "execute_code"

    # Inject ADR-0046 compliant artifact scanner via try/finally
    wrapped_code = (
        "try:\n"
        + textwrap.indent(code, "    ")
        + "\nfinally:\n"
        + textwrap.indent(_ARTIFACT_SCANNER, "    ")
    )

    exec_result = await runtime.execute(
        wrapped_code,
        language=lang if lang in {"python", "py"} else "python",
        timeout_s=timeout_s,
        invocation_id=inv,
    )
    ok = exec_result.success
    state: dict[str, Any] = {
        "success": ok,
        "language": lang,
        "output": exec_result.stdout,
        "stderr": exec_result.stderr,
        "exitCode": exec_result.exit_code,
        "code": code,  # source code always visible in tool card
    }
    if not ok:
        state["error"] = exec_result.error_summary or exec_result.error
    content = exec_result.stdout or exec_result.stderr or ("ok" if ok else state.get("error", ""))
    return ComputerOpResult(
        success=ok,
        content=str(content),
        state=state,
        error=str(state.get("error") or ""),
        exec_result=exec_result,
        generated_files=exec_result.generated_files,  # pipe through
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_onlyboxes_sandbox.py::ExecuteCodeArtifactTests -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `uv run pytest tests/test_onlyboxes_sandbox.py tests/test_computer_tools.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add lca/layer0_infra/computer/runtime_exec.py tests/test_onlyboxes_sandbox.py
git commit -m "fix(exec): inject ADR-0046 artifact scanner in execute_code

- _ARTIFACT_SCANNER scans only /mnt/data/outputs/ (not /mnt/data/ root)
- try/finally wrapping ensures harvest even on user code exception
- state['code'] carries source for frontend display (success or failure)
- generated_files piped from SandboxExecResult to ComputerOpResult"
```

---

### Task 4: PDF previewable + verification

**Files:**
- Modify: `lca/layer0_infra/file_store.py:73-78`
- Test: `tests/test_file_store_and_write_tool.py`

- [ ] **Step 1: Write failing test — PDF is previewable**

Add to `tests/test_file_store_and_write_tool.py`:

```python
def test_pdf_is_previewable() -> None:
    from lca.layer0_infra.file_store import _is_previewable

    assert _is_previewable("application/pdf") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_file_store_and_write_tool.py -k test_pdf_is_previewable -v`
Expected: FAIL

- [ ] **Step 3: Add `application/pdf` to previewable MIME set**

In `lca/layer0_infra/file_store.py`, modify `_is_previewable()`:

```python
if mime in {
    "application/json",
    "application/javascript",
    "application/xml",
    "application/xhtml+xml",
    "application/pdf",  # new
}:
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_file_store_and_write_tool.py -k test_pdf_is_previewable -v`
Expected: PASS

- [ ] **Step 5: Full verification pipeline**

```bash
uv run ruff check --fix .
uv run ruff format .
uv run lint-imports
uv run mypy lca
uv run pytest
uv run vulture lca --min-confidence 80
```

Expected: All pass. If `vulture` flags `_ARTIFACT_SCANNER` as unused (it's a module-level constant used via string interpolation), add `# noqa: F841` or a `__all__` entry.

- [ ] **Step 6: Commit**

```bash
git add lca/layer0_infra/file_store.py tests/test_file_store_and_write_tool.py
git commit -m "feat(storage): add application/pdf to previewable MIME types

PDF files stored in FileStore are now marked as previewable,
enabling frontend inline rendering via LobeHub FileViewer."
```

---

### Task 5: Final verification + dead code note

- [ ] **Step 1: Run complete verification**

```bash
uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run pytest && uv run vulture lca --min-confidence 80
```

- [ ] **Step 2: Verify architecture contract (import-linter)**

The 5-layer contract must still hold — no new cross-layer violations:

```bash
uv run lint-imports
```

Expected: "Is satisfied" for all contracts.

- [ ] **Step 3: Verify no regression in existing sandbox tests**

```bash
uv run pytest tests/test_onlyboxes_sandbox.py tests/test_computer_tools.py tests/test_file_store_and_write_tool.py -v
```

- [ ] **Step 4: If all green, final commit**

No new commit needed — all changes already committed per-task. Just confirm clean tree:

```bash
git status  # should be clean
git log --oneline -5  # should show the 4 task commits
```
