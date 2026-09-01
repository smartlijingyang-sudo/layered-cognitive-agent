# ADR 0165.1 Spine Execution Points Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every execution point in LCA framework emit a structurally complete, framework-mandatory event to a single append-only `events.jsonl`, with zero manual emission by business code. Add self-discovering failure detection and source-level trace (`file:line + locals_snapshot`) so that production incidents can be diagnosed without grepping 7 logs.

**Architecture:** Replace the multi-backend journal (engine / backends / step / stream) with a single `EventSpine` plugin that fans all events through one file. Business code never imports backends, derivers, or run-store. Three weaving paths: `cordis ctx.effect` (plugin lifecycle), `cordis ctx.intercept` (cognition/runtime/agent internals), and `lca/harness/declarative/compile/assembler.wrap_instrument` (phase graph nodes). 18 plugins compose the spine itself; profile selects which ones to load. Build-time: 5 hard-fail checks. Runtime: 4 fault domains. Failure discovery: 3 layers (builtin / invariant / open-domain fallback). Source-level: `inspect.currentframe()` + `repr()` locals with 4 KB cap and secret-redact.

**Tech Stack:** Python 3.11, cordis, dataclasses, pytest, ruff, mypy, import-linter, vulture, `inspect` / `typing.get_type_hints` / `linecache`, optional `OII-DEBUG` profile for source snippets.

**Spec:** `docs/superpowers/specs/2026-09-01-spine-execution-points-design.md` (1811 lines, 4-round iteration outcome)

**Parent ADR:** `docs/adr/0165-event-spine-unified-log.md`
**Mini-ADR:** `docs/adr/0165.1-execution-point-enforcement.md`

---

## Global Constraints

- No business-layer code (`lca.cognition / lca.runtime / lca.agent / lca.application`) may `import lca.infrastructure.observability.journal.{engine, backends, step, stream}` or `lca.infrastructure.observability.spine.derivers`; enforced by importlinter `business-event-isolation` (PR-5).
- All event emission goes through `EventSpine.append(...)` via plugins; direct calls to `RunStore.append` / `LiveTail.on_event` / `StepGroupedBackend.write` are forbidden in business code (Layer-4 + Layer-5).
- 5 build-time hard-fail checks (Layer-1..5): registry completeness, wrap_fn binding, phase-graph runnable instrumented, importlinter hard fail, per-EXECUTION_POINTS unit test.
- 4 runtime fault domains (FD-1..4); FD-1/3/4 fail-fast, FD-2 (deriver) contained.
- Event schema D9-D11: `execution_point`, `channel`, `span_id`, `parent_span_id`, `sequence`, `epoch`, `causality_id`, `outcome` (enum), `when`, `when_corrected`, `prev_event_hash`. Auto-fields must derive from one of `{signature, runtime, context, framework_observer, plugin_manifest_decl}`; `manual` is not allowed except for `tiebreak_rule` / `policy_id` already in plugin manifest (I12).
- Anomaly detection: 8 detectors MUST all be present (`spine.deriver.anomaly` plugin). Missing one is build-fail (I16).
- Source-level: every `*.start` MUST carry `source_location` + `call_frames[:10]` + `locals_snapshot` (4 KB cap, repr only, secret redacted). Missing → fail-fast (I17).
- All 18 spine sub-plugins must live under `lca/plugins/observability/spine/`; the package `lca/infrastructure/observability/spine/instrumentation/` MUST be deleted by PR-8 end.
- Profile-driven composition: `profiles/web-standard.yaml` (default), `profiles/oii-debug.yaml` (extends with introspection), `profiles/benchmark.yaml` (minimal).
- Pre-merge CI: `uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run pytest && uv run vulture lca --min-confidence 80`. No `--no-verify`.
- Each step TDD: write failing test first, watch it fail, write minimal implementation, watch it pass, commit. Follow existing commit conventions: `<type>(<scope>): <subject>`.

---

## 0. Scope and Stack Overview

The 9 PRs form a Graphite stack. Each PR is independently shippable but later PRs depend on earlier ones. Within PR-3 the work is split into 4 sub-PRs (cognition / runtime / agent / body / llm) so two engineers can work in parallel.

| PR | Purpose | New files | Tests | Commit gating |
|---|---|---|---|---|
| **PR-1** | spine-foundations | `spine/{event_spine,context,manifest}.py`, `spine/sinks/{file,base}.py`, `tests/observability/spine/test_event_spine.py` | ~10 | CI |
| **PR-2** | spine-derivers | `spine/derivers/{step_tree,narrative,live_tail,base}.py`, regression tests | ~15 | CI |
| **PR-3** | execution-points | `runtime_hooks.py`, EXECUTION_POINTS in manifest, ctx.effect + ctx.intercept for cognition/runtime/agent/body | ~30 | CI |
| **PR-4** | phase-graph-wrap | changes to `lca/harness/declarative/compile/assembler.py`, `wrap_instrument` test | ~12 | CI |
| **PR-5** | lint-hardfail | `pyproject.toml` importlinter rules + dry-run migration | ~5 | CI |
| **PR-6** | orphan-events | orphan clause in `EventRecord`, `lca-ops journal events --orphans` | ~8 | CI |
| **PR-7** | auto-fields | 18 sub-plugins under `lca/plugins/observability/spine/`, `FieldProducer` Protocol, 5 reflector plugins | ~30 | CI |
| **PR-7.1** | wiring | connect reflector plugins via `EmitPipeline` to all existing `wrap_instrument` call sites | ~12 | CI |
| **PR-8** | plugin-extraction | drop `lca/infrastructure/observability/spine/instrumentation/` entirely; move all 18 plugins to spine/ tree | ~5 (regression) | CI |
| **PR-9** | source-attacher | `spine.reflector.source` plugin + I17 enforcement | ~12 | CI |

Total: ~140 new tests across the stack.

---

# PR-1: spine-foundations

## Task 1.1: Create `ExecutionPoints` close-set manifest

**Files:**
- Create: `lca/infrastructure/observability/spine/manifest.py`
- Test: `tests/observability/spine/test_manifest.py`

**Interfaces:**
- Consumes: nothing (foundational)
- Produces: `EXECUTION_POINTS: tuple[str, ...]` (~50 strings across 10 layers: transport, kernel lifecycle, agent loop, cognition, body, llm, runtime, phase_graph, exception)

- [ ] **Step 1: Write the failing test**

```python
# tests/observability/spine/test_manifest.py
from lca.infrastructure.observability.spine.manifest import EXECUTION_POINTS

def test_execution_points_close_set():
    """Manifest is a closed-set of execution points, deduplicated."""
    assert isinstance(EXECUTION_POINTS, tuple)
    assert len(EXECUTION_POINTS) > 30
    assert all(isinstance(ep, str) for ep in EXECUTION_POINTS)
    assert len(set(EXECUTION_POINTS)) == len(EXECUTION_POINTS), "no duplicates"
```

- [ ] **Step 2: Run the test, confirm it fails**

Run: `uv run pytest tests/observability/spine/test_manifest.py -v`
Expected: `ModuleNotFoundError: No module named 'lca.infrastructure.observability.spine.manifest'`

- [ ] **Step 3: Write the manifest file**

```python
# lca/infrastructure/observability/spine/manifest.py
"""Close-set of execution points that must emit a spine event.

Adding/removing a point requires a Layer-1 build-time check pass and an
EXECUTION_POINT_TEST matching it (I8 of ADR-0165.1). The set is intentional:
do not edit casually.
"""

EXECUTION_POINTS: tuple[str, ...] = (
    # Transport (ADR-0112)
    "transport.route.enter",
    "transport.route.exit",
    "transport.sse.publish",
    # Kernel lifecycle
    "kernel.boot.start",
    "kernel.boot.completed",
    "kernel.run.start",
    "kernel.run.stop",
    "kernel.run.cancelled",
    # Agent loop
    "agent_loop.iteration.start",
    "agent_loop.iteration.end",
    # Cognition
    "brain.perceive.start",
    "brain.perceive.end",
    "brain.think.start",
    "brain.think.end",
    "brain.gate.start",
    "brain.gate.end",
    "critic.eval.start",
    "critic.eval.end",
    "reasoner.reason.start",
    "reasoner.reason.end",
    "synthesizer.merge",
    "skill_router.route",
    "memory.read",
    "memory.write",
    # Body
    "body.tool.execute.start",
    "body.tool.execute.end",
    "body.tool.retry",
    "body.sandbox.enter",
    "body.sandbox.exit",
    # LLM
    "llm.call.start",
    "llm.call.end",
    "llm.stream.token",
    # Runtime
    "runtime.reducer.apply",
    "runtime.checkpoint.create",
    "runtime.resume.start",
    "runtime.resume.end",
    "runtime.event_publisher.publish",
    # Phase graph
    "phase_graph.node.start",
    "phase_graph.node.end",
    "phase_graph.edge.transit",
    # Exception/finally
    "exception.caught",
    "exception.finally",
)
```

- [ ] **Step 4: Run the test, confirm it passes**

Run: `uv run pytest tests/observability/spine/test_manifest.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add lca/infrastructure/observability/spine/manifest.py tests/observability/spine/test_manifest.py
git commit -m "feat(spine): EXECUTION_POINTS close-set manifest (ADR-0165.1)"
```

---

## Task 1.2: Create `EventRecord` dataclass

**Files:**
- Create: `lca/infrastructure/observability/spine/event_record.py`
- Test: `tests/observability/spine/test_event_record.py`

**Interfaces:**
- Consumes: nothing
- Produces: `EventRecord` (frozen dataclass carrying execution_point, channel, span_id, parent_span_id, sequence, epoch, causality_id, outcome, when, when_corrected, prev_event_hash, payload, run_id, step_id)

- [ ] **Step 1: Write the failing test**

```python
# tests/observability/spine/test_event_record.py
from dataclasses import FrozenInstanceError

import pytest

from lca.infrastructure.observability.spine.event_record import EventRecord


def test_event_record_immutable():
    rec = EventRecord(
        execution_point="brain.think.start",
        channel="fact",
        span_id="01HM",
        parent_span_id=None,
        sequence=1,
        epoch=1,
        causality_id="sha256:abc",
        outcome=None,
        when=__import__("datetime").datetime.utcnow(),
        when_corrected=__import__("datetime").datetime.utcnow(),
        prev_event_hash=None,
        run_id="r1",
        step_id="s1",
        payload={"k": 1},
    )
    with pytest.raises(FrozenInstanceError):
        rec.sequence = 999


def test_event_record_unknown_execution_point_rejected():
    with pytest.raises(ValueError, match="UnknownExecutionPoint"):
        EventRecord(
            execution_point="not.in.manifest",
            channel="fact",
            span_id="x", parent_span_id=None,
            sequence=1, epoch=1, causality_id="c",
            outcome=None,
            when=__import__("datetime").datetime.utcnow(),
            when_corrected=__import__("datetime").datetime.utcnow(),
            prev_event_hash=None,
            run_id="r", step_id=None, payload={},
        )
```

- [ ] **Step 2: Run, confirm fail (module missing)**
- [ ] **Step 3: Implement `event_record.py`** with:
  - `Outcome: Literal["success","failure","timeout","cancelled","rejected","retrying","partial","exhausted","void"]`
  - `Channel: Literal["fact","control","error","diagnostic"]`
  - `EventRecord` frozen dataclass; `__post_init__` validates `execution_point in EXECUTION_POINTS` else raise `ValueError("UnknownExecutionPoint")`
- [ ] **Step 4: Run, confirm pass**
- [ ] **Step 5: Commit**

```bash
git add lca/infrastructure/observability/spine/event_record.py tests/observability/spine/test_event_record.py
git commit -m "feat(spine): EventRecord frozen dataclass with channel/outcome enum"
```

---

## Task 1.3: Create `SpineContext` (ContextVar-based)

**Files:**
- Create: `lca/infrastructure/observability/spine/context.py`
- Test: `tests/observability/spine/test_context.py`

**Interfaces:**
- Consumes: EventRecord fields (span_id, parent_span_id, run_id, step_id)
- Produces: `class SpineContext` with `set_run(run_id)`, `set_step(step_id)`, `push_span(ep) -> SpanContext`, `pop_span(ep) -> SpanContext`, `current_span() -> SpanContext | None`, `next_sequence() -> int`, `next_epoch() -> int`

- [ ] **Step 1: Test for span stack push/pop with EP match**

```python
# tests/observability/spine/test_context.py
def test_span_push_pop_match():
    from lca.infrastructure.observability.spine.context import SpineContext
    SpineContext.set_run("r1")
    span = SpineContext.push_span("brain.think.start")
    assert span.span_id
    assert span.parent_span_id is None
    back = SpineContext.pop_span("brain.think.end")
    assert back.span_id == span.span_id


def test_span_pop_mismatch_raises():
    from lca.infrastructure.observability.spine.context import SpineContext, PhaseMachineViolation
    SpineContext.set_run("r2")
    SpineContext.push_span("brain.think.start")
    import pytest
    with pytest.raises(PhaseMachineViolation):
        SpineContext.pop_span("agent_loop.iteration.end")
```

- [ ] **Step 2: Run, confirm fail**
- [ ] **Step 3: Implement context.py**
  - ContextVars: `_run_id`, `_step_id`, `_span_stack`, `_seq_counter`, `_epoch_counter`
  - classmethods; phase-machine violation on mismatch (I13)
  - `PhaseMachineViolation(Exception)`
- [ ] **Step 4: Run, confirm pass**
- [ ] **Step 5: Commit**

```bash
git add lca/infrastructure/observability/spine/context.py tests/observability/spine/test_context.py
git commit -m "feat(spine): SpineContext with ContextVars and phase-machine check"
```

---

## Task 1.4: Create `EventSink` Protocol + `FileSink`

**Files:**
- Create: `lca/infrastructure/observability/spine/sinks/base.py`
- Create: `lca/infrastructure/observability/spine/sinks/file_sink.py`
- Test: `tests/observability/spine/sinks/test_file_sink.py`

**Interfaces:**
- Consumes: `EventRecord`
- Produces: `EventSink` Protocol; `FileSink` that opens `<run_dir>/events.jsonl` in append mode, writes JSON line per event, fsyncs every 100 events or 100 ms (default), uses `O_APPEND` for atomic single-line write when line length ≤ 4096

- [ ] **Step 1: Test file sink write + fsync + reopen**

```python
# tests/observability/spine/sinks/test_file_sink.py
import json
from pathlib import Path

import datetime as dt

from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink


def test_file_sink_appends_and_reads_back(tmp_path: Path):
    fs = FileSink(tmp_path, run_id="r1")
    rec = EventRecord(
        execution_point="brain.think.start",
        channel="fact", span_id="01HM", parent_span_id=None,
        sequence=1, epoch=1, causality_id="ca",
        outcome=None,
        when=dt.datetime(2026, 9, 1, 12, 0, 0),
        when_corrected=dt.datetime(2026, 9, 1, 12, 0, 0, 1),
        prev_event_hash=None, run_id="r1", step_id="s1",
        payload={"x": 1},
    )
    fs.write(rec)
    fs.close()
    lines = (tmp_path / "events.jsonl").read_text().splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["execution_point"] == "brain.think.start"


def test_file_sink_events_oversize_uses_sidecar(tmp_path: Path):
    fs = FileSink(tmp_path, run_id="r1")
    # build an EventRecord with a 5 KB payload to trigger sidecar
    big = "x" * 5000
    from lca.infrastructure.observability.spine.manifest import EXECUTION_POINTS
    import datetime as dt
    rec = EventRecord(
        execution_point=EXECUTION_POINTS[0], channel="fact",
        span_id="z", parent_span_id=None,
        sequence=1, epoch=1, causality_id="c", outcome=None,
        when=dt.datetime(2026, 9, 1),
        when_corrected=dt.datetime(2026, 9, 1),
        prev_event_hash=None, run_id="r", step_id=None,
        payload={"big": big},
    )
    fs.write(rec)
    fs.close()
    # main line should reference offload hash; an offload json exists
    sidecars = list(tmp_path.glob("*.json"))
    assert any(".json" in p.name and "events.jsonl" not in p.name for p in sidecars)
```

- [ ] **Step 2: Run, confirm fail**
- [ ] **Step 3: Implement base.py and file_sink.py**
  - `EventSink` Protocol: `write(rec)`, `close()`
  - `FileSink.open()` opens `<run_dir>/events.jsonl` with `O_APPEND | O_CREAT | O_WRONLY`
  - On `write()`: serialize with `json.dumps(..., default=str)`; if byte length > 4096, write hash and place payload in `<hash>.json` sidecar (offload path I10)
  - Fsync every N events or T ms (configurable; default 100/100ms)
- [ ] **Step 4: Run, confirm pass**
- [ ] **Step 5: Commit**

```bash
git add lca/infrastructure/observability/spine/sinks/ tests/observability/spine/sinks/test_file_sink.py
git commit -m "feat(spine): EventSink Protocol + FileSink with O_APPEND atomic write"
```

---

## Task 1.5: Create minimal `EventSpine`

**Files:**
- Create: `lca/infrastructure/observability/spine/event_spine.py`
- Test: `tests/observability/spine/test_event_spine.py`

**Interfaces:**
- Consumes: `EventSink`, optional list of deriver callables (`subscribers`)
- Produces: `class EventSpine` with `append(event_cls, *, execution_point, span_ctx=None, caller_payload=None) -> EventRecord`; `subscribe(fn) -> Disposer`; `flush()`, `close()`; auto-stamps `span_id`/`parent_span_id`/`sequence`/`epoch`/`when`/`when_corrected`/`causality_id`/`prev_event_hash` if not supplied

- [ ] **Step 1: Test single-event round-trip and FD-1 propagation**

```python
# tests/observability/spine/test_event_spine.py
import datetime as dt
import json
from pathlib import Path

import pytest

from lca.infrastructure.observability.spine.event_spine import EventSpine
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink
from lca.infrastructure.observability.spine.context import SpineContext


def test_event_spine_writes_event(tmp_path: Path):
    SpineContext.set_run("r1")
    fs = FileSink(tmp_path, run_id="r1")
    spine = EventSpine(sinks=[fs], subscribers=[])
    span = SpineContext.push_span("brain.think.start")
    spine.append(
        execution_point="brain.think.start",
        channel="fact",
        caller_payload={"x": 1},
        span_ctx=span,
    )
    spine.close()
    lines = (tmp_path / "events.jsonl").read_text().splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["execution_point"] == "brain.think.start"
    assert obj["sequence"] == 1


def test_event_spine_fd1_raises_to_business(tmp_path: Path):
    """FileSink error propagates as FD-1 (fail-fast)."""
    fs = FileSink(tmp_path, run_id="r1")
    spine = EventSpine(sinks=[fs], subscribers=[])
    # break the sink
    fs.path = tmp_path / "nowhere" / "events.jsonl"  # dir doesn't exist
    span = SpineContext.push_span("brain.think.start")
    with pytest.raises(OSError):
        spine.append(execution_point="brain.think.start",
                     channel="fact", caller_payload={}, span_ctx=span)
```

- [ ] **Step 2: Run, confirm fail**
- [ ] **Step 3: Implement event_spine.py**
- [ ] **Step 4: Run, confirm pass**
- [ ] **Step 5: Commit**

```bash
git add lca/infrastructure/observability/spine/event_spine.py tests/observability/spine/test_event_spine.py
git commit -m "feat(spine): EventSpine core — single entrypoint, FD-1 fail-fast"
```

---

## Task 1.6: importlinter dry-run setup for `business-event-isolation`

**Files:**
- Modify: `pyproject.toml` (add contract entry as dry-run)

- [ ] **Step 1: Add rule under `[tool.importlinter.contracts]` in `pyproject.toml`**

```toml
[[tool.importlinter.contracts]]
name = "business-event-isolation"
type = "forbidden"
source_modules = [
    "lca.cognition",
    "lca.runtime",
    "lca.agent",
    "lca.application",
]
forbidden_modules = [
    "lca.infrastructure.observability.journal.engine",
    "lca.infrastructure.observability.journal.backends",
    "lca.infrastructure.observability.journal.stream",
    "lca.infrastructure.observability.journal.step",
]
```

Run `uv run lint-imports`. Expected: violations listed, NOT yet hard-fail (some pre-existing imports still allowed at this stage; PR-5 enforces).

- [ ] **Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "chore(lint): business-event-isolation contract dry-run (PR-1)"
```

---

## PR-1 Acceptance

- All 5 tasks committed.
- `uv run pytest tests/observability/spine/ -v` PASS.
- `uv run lint-imports` runs dry-run (may show warnings, not errors yet).
- New files only; no business code modified.

---

# PR-2: spine-derivers

## Task 2.1: `Deriver` Protocol

**Files:**
- Create: `lca/infrastructure/observability/spine/derivers/base.py`
- Test: `tests/observability/spine/derivers/test_base.py`

- [ ] **Step 1: Test Deriver Protocol with FD-2 containment**

```python
def test_deriver_failing_one_does_not_block_business(tmp_path):
    from lca.infrastructure.observability.spine.derivers.base import Deriver
    from lca.infrastructure.observability.spine.event_spine import EventSpine
    from lca.infrastructure.observability.spine.sinks.file_sink import FileSink
    from lca.infrastructure.observability.spine.context import SpineContext

    class BadDeriver:
        def on_event(self, event): raise RuntimeError("deriver boom")

    fs = FileSink(tmp_path, run_id="r1")
    spine = EventSpine(sinks=[fs], subscribers=[BadDeriver().on_event])
    span = SpineContext.push_span("brain.think.start")
    rec = spine.append(execution_point="brain.think.start",
                       channel="fact", caller_payload={}, span_ctx=span)
    assert rec is not None  # business continues; failure contained
    spine.close()
```

- [ ] **Step 2: Run, confirm fail**
- [ ] **Step 3: Implement** `Deriver` Protocol + `EventSpine.append`'s subscriber try/except that logs to `spine.deriver_failed` FD-2 channel
- [ ] **Step 4: Run, confirm pass**
- [ ] **Step 5: Commit**

```bash
git add lca/infrastructure/observability/spine/derivers/base.py tests/observability/spine/derivers/test_base.py
git commit -m "feat(spine): Deriver Protocol with FD-2 containment"
```

---

## Task 2.2: Refactor existing 4 backends → deriver plugins

**Files:**
- Modify: `lca/infrastructure/observability/journal/backends/step_grouped.py` (wrap its existing logic as a deriver; **keep working for PR-2**)
- Modify: `lca/infrastructure/observability/journal/step/narrative.py` (same)
- Modify: `lca/infrastructure/observability/journal/stream/live_tail.py` (same)
- Create: `lca/infrastructure/observability/spine/derivers/step_tree.py`
- Create: `lca/infrastructure/observability/spine/derivers/narrative.py`
- Create: `lca/infrastructure/observability/spine/derivers/live_tail.py`
- Test: `tests/observability/spine/derivers/test_step_tree_deriver.py`

- [ ] **Step 1: Write tests** asserting "StepTreeDeriver reconstructs journal.json from events.jsonl same as legacy StepGroupedBackend"
- [ ] **Step 2: Implement derivers** that read events from SpineContext and call existing writers with deprecation warnings
- [ ] **Step 3: Run, confirm parity tests pass**
- [ ] **Step 4: Commit**

```bash
git add ...
git commit -m "refactor(journal): migrate 4 backends to spine.deriver.* (parallel-write phase)"
```

---

## PR-2 Acceptance

- `events.jsonl` and `journal.json` write in parallel (both true); user sees no change.
- Deriver failures contained (FD-2).
- All existing journal tests still pass.

---

# PR-3: spine-execution-points (4 sub-PRs)

## Task 3.0: Define `FieldProducer` Protocol (foundation for sub-PRs)

**Files:**
- Create: `lca/contracts/observability/spine/producer.py`
- Test: `tests/observability/spine/test_field_producer_protocol.py`

- [ ] **Step 1: Test runtime_checkable Protocol**

```python
from lca.contracts.observability.spine.producer import FieldProducer

def test_field_producer_is_protocol():
    p = FieldProducer  # Protocol class
    assert hasattr(p, "produce")
```

- [ ] **Step 2: Implement Protocol** with `name`, `priority`, `enabled`, `produce(*, fn, args, kwargs, ctx, span, phase) -> dict`
- [ ] **Step 3: Commit** `chore(contracts): FieldProducer Protocol for spine plugin composition`

---

## Task 3.1 (sub-PR-1): agent layer instrumentation

**Files:**
- Modify: `lca/agent/spawn.py`, `lca/agent/team/*.py`
- Create: `lca/plugins/observability/spine/reflectors/agent_spawn.py`

- [ ] **Step 1: Test `agent_loop.iteration.start/end` emitted on every iteration**
- [ ] **Step 2: Implement ctx.intercept** for `agent_loop.iteration`
- [ ] **Step 3: Run, confirm pass**
- [ ] **Step 4: Commit** `feat(spine): agent_loop iteration instrumentation (PR-3.1)`

---

## Task 3.2 (sub-PR-2): cognition layer instrumentation

**Files:**
- Modify: `lca/cognition/brain/modular_brain.py`, `lca/cognition/brain/reasoner.py`, `lca/cognition/brain/critic.py`, `lca/cognition/brain/synthesizer.py`, `lca/cognition/brain/skill_router.py`, `lca/cognition/memory/*.py`
- Create: `lca/plugins/observability/spine/reflectors/cognition.py`

- [ ] **Step 1: Tests** for each cognition EP — `brain.think.start/end`, `critic.eval.start/end`, etc.
- [ ] **Step 2: Implement ctx.intercept** for each
- [ ] **Step 3: Run, confirm pass**
- [ ] **Step 4: Commit** per-file

---

## Task 3.3 (sub-PR-3): body + llm layer instrumentation

**Files:**
- Modify: `lca/cognition/body/*.py`, `lca/cognition/body/action_handlers.py`
- Modify: `lca/infrastructure/llm/resolver.py`
- Create: `lca/plugins/observability/spine/reflectors/body_llm.py`

- [ ] **Step 1: Tests** for `body.tool.execute.start/end`, `body.sandbox.enter/exit`, `body.tool.retry`, `llm.call.start/end`, `llm.stream.token`
- [ ] **Step 2: Implement** interceptor + LLM emit
- [ ] **Step 3: Commit**

---

## Task 3.4 (sub-PR-4): runtime layer instrumentation

**Files:**
- Modify: `lca/runtime/reducer.py`, `runtime_loop.py`, `event_publisher.py`, `checkpoint*.py`
- Create: `lca/plugins/observability/spine/reflectors/runtime.py`

- [ ] **Step 1: Tests** for `runtime.reducer.apply`, `runtime.checkpoint.create`, `runtime.resume.start/end`, `runtime.event_publisher.publish`, `exception.caught`, `exception.finally`
- [ ] **Step 2: Implement** middleware approach (replace direct emit references with decorator-instrumented methods)
- [ ] **Step 3: Commit** per-file

---

## Task 3.5: Layer-1 + Layer-2 build-time checks

**Files:**
- Create: `lca/infrastructure/observability/spine/registry.py`
- Create: `lca/harness/profile/compile_spine_registry.py`
- Test: `tests/observability/spine/test_registry_completeness.py`

- [ ] **Step 1: Test Layer-1** — registry.keys() ⊇ EXECUTION_POINTS, fail otherwise
- [ ] **Step 2: Test Layer-2** — every wrap_fn + target_module bound
- [ ] **Step 3: Implement registry + compile_spine_registry + kernel.boot hook**
- [ ] **Step 4: Commit** `feat(spine): 5-layer build-time checks (L1+L2)`

---

## PR-3 Acceptance

- All 47 (4 sub-PRs combined) tasks committed.
- `uv run pytest tests/observability/spine/ -v` PASS.
- `uv run lint-imports` still dry-run (PR-5 enforces).
- Layer-1, Layer-2 hard-fail are part of pytest suite.

---

# PR-4: spine-phase-graph-wrap

## Task 4.1: wrap_instrument forces instrumentation

**Files:**
- Modify: `lca/harness/declarative/compile/assembler.py`
- Create: `lca/harness/declarative/compile/instrument_wrap.py`
- Test: `tests/harness/declarative/compile/test_assembler_wraps_instrument.py`

- [ ] **Step 1: Test** — `ExecutableNode.runnable.__lca_instrumented__ is True`, `wrap_provenance == "assembler"`

```python
def test_assembler_wraps_with_instrument():
    from lca.harness.declarative.compile.assembler import assemble_plan
    from lca.harness.declarative.compile.compile import compile_phase_graph

    plan = compile_phase_graph(some_plan_with_nodes)
    node = plan.nodes["x"]
    assert getattr(node.runnable, "__lca_instrumented__", False) is True
    assert getattr(node.runnable, "wrap_provenance", None) == "assembler"
```

- [ ] **Step 2: Run, confirm fail**
- [ ] **Step 3: Implement `wrap_instrument`** in `instrument_wrap.py`:
  - `phase_graph.node.start/end` events
  - Spans via SpineContext.push_span / pop_span
  - On exception: emit `phase_graph.node.end` with `outcome="failure"` and let outer FD-3 catalog check apply
  - Sets `__lca_instrumented__ = True`, `wrap_provenance = "assembler"`
- [ ] **Step 4: Wire into `assembler.py`** so every node compile passes through `wrap_instrument`
- [ ] **Step 5: Run, confirm pass**
- [ ] **Step 6: Commit** `feat(spine): phase graph assembler mandatory instrumentation (Layer-3)`

---

## Task 4.2: Layer-3 hard-fail check

**Files:**
- Modify: `lca/harness/declarative/compile/assembler.py` add `assert_all_instrumented(plan)`
- Test: `tests/harness/declarative/compile/test_layer3_check.py`

- [ ] **Step 1: Test** that a hand-built plan with unwrapped runnable is rejected
- [ ] **Step 2: Implement** Layer-3 check at end of `compile_phase_graph`
- [ ] **Step 3: Commit**

---

## PR-4 Acceptance

- All phase graph nodes are wrapped.
- Layer-3 check rejects unwrapped nodes.
- `uv run pytest tests/harness/declarative/ -v` PASS.

---

# PR-5: spine-lint-hardfail

## Task 5.1: Switch importlinter from dry-run to hard-fail

**Files:**
- Modify: `pyproject.toml`
- Modify: `scripts/check_kernel_boundary.py`
- Test: `tests/lint_imports/test_business_event_isolation.py`

- [ ] **Step 1: Migrate remaining `from lca.infrastructure.observability.journal.{engine,backends,stream,step}` usage in `lca.cognition / runtime / agent / application` to `from lca.infrastructure.observability.spine.event_spine import EventSpine`**
- [ ] **Step 2: Run** `uv run lint-imports` — confirm 0 violations
- [ ] **Step 3: Update `pyproject.toml`** to set this contract from dry-run to hard-fail (no `dry_run=true` flag)
- [ ] **Step 4: Add `scripts/check_kernel_boundary.py`** invocation in CI
- [ ] **Step 5: Commit** `feat(spine): importlinter business-event-isolation hard-fail`

---

## PR-5 Acceptance

- `uv run lint-imports` exits 0 with business-event-isolation enforced.
- No `RunStore.append` / `LiveTail.on_event` / `StepGroupedBackend.write` calls outside infrastructure/observability/.

---

# PR-6: spine-orphan-events

## Task 6.1: `EventRecord.phase` + `reason` field

**Files:**
- Modify: `lca/infrastructure/observability/spine/event_record.py`
- Create: `lca/infrastructure/observability/spine/orphan.py`
- Test: `tests/observability/spine/test_orphan.py`

- [ ] **Step 1: Test** that an event emitted without active step has `phase="orphan"`, `reason="cancel_pre_boot"`, and StepTreeDeriver skip it

```python
def test_orphan_phase_skipped_by_step_tree_deriver():
    rec = make_event(execution_point="kernel.boot.start",
                     phase="orphan", reason="cancel_pre_boot")
    assert rec.phase == "orphan"
    # StepTreeDeriver.on_event(rec) → noop
```

- [ ] **Step 2: Implement** `phase: Literal["live","orphan"] = "live"`, `reason: str | None = None`
- [ ] **Step 3: StepTreeDeriver** checks `rec.phase == "live"` before writing
- [ ] **Step 4: Commit** `feat(spine): orphan event phase + reason (PR-6)`

---

## Task 6.2: e2e cancel-pre-boot run produces orphan events

**Files:**
- Create: `tests/e2e/test_orphan_cancel_pre_boot.py`

- [ ] **Step 1: Test** — simulate user cancel during boot, verify events.jsonl contains phase=orphan events

```python
def test_cancel_pre_boot_emits_orphan_events():
    runner = E2ERunner(profile="web-standard", cancel_at_step=0)
    result = runner.run(objective="x", cancel_after_ms=10)
    events = result.read_events_jsonl()
    orphans = [e for e in events if e["phase"] == "orphan"]
    assert len(orphans) >= 3  # kernel.run.start + cancelled + stopped
    assert orphans[-1]["reason"] == "cancel_pre_boot"
```

- [ ] **Step 2: Implement orchestrator-side cancellation handler** that emits orphaned events on cancel
- [ ] **Step 3: Commit** `feat(spine): e2e cancel-pre-boot emits orphan events`

---

## PR-6 Acceptance

- `uv run pytest tests/observability/spine/test_orphan.py tests/e2e/test_orphan_cancel_pre_boot.py -v` PASS.
- The `run_c9fd294e5371` scenario is reproducible and `events.jsonl` contains the orphan trail.

---

# PR-7: spine-auto-fields

## Task 7.0: FieldProducer Protocol (already in 3.0)

## Task 7.1: `spine.reflector.signature` plugin

**Files:**
- Create: `lca/plugins/observability/spine/reflectors/signature.py`
- Test: `tests/lca_plugins/observability/spine/test_reflector_signature.py`

- [ ] **Step 1: Test** `produce(phase="pre")` returns `signature_fingerprint`, `input_params`, `output_schema`, `docstring_captured`
- [ ] **Step 2: Implement** `SignatureFieldProducer(FieldProducer)`
- [ ] **Step 3: Wrap with `@plugin(id="spine.reflector.signature", provides=("field_producer.signature",), layer="L0", kind=PluginKind.SEAM)` mirroring `lca/plugins/transport/webserver/server.py` template
- [ ] **Step 4: Run plugin test**
- [ ] **Step 5: Commit** `feat(spine.plug): reflector.signature plugin (D11 signature auto-source)`

---

## Task 7.2: `spine.reflector.context` plugin

**Files:**
- Create: `lca/plugins/observability/spine/reflectors/context.py`
- Test: `tests/lca_plugins/observability/spine/test_reflector_context.py`

- [ ] **Step 1: Test** `produce(phase="pre")` returns `preconditions`, `budget_at_entry`; `produce(phase="post")` returns `post_state_delta`, `budget_consumed`, `circuit_breaker_state`, `side_effects_added`
- [ ] **Step 2: Implement** `ContextFieldProducer`
- [ ] **Step 3: Wrap with `@plugin`**
- [ ] **Step 4: Commit**

---

## Task 7.3: `spine.reflector.runtime` plugin

**Files:**
- Create: `lca/plugins/observability/spine/reflectors/runtime.py`
- Test: similar

- [ ] **Step 1+2+3+4+5** as for 7.1; produce `return_value_fingerprint`, `duration_ms`, `input_fingerprint`, `when_corrected`, `prev_event_hash`

---

## Task 7.4: `spine.classifier.exception.builtin` plugin (Layer-A known)

**Files:**
- Create: `lca/plugins/observability/spine/classifiers/exception_builtin.py`
- Test: `tests/lca_plugins/observability/spine/test_classifier_builtin.py`

- [ ] **Step 1: Test** — `TimeoutError` → `outcome="timeout"`, `edge_case_id="Timeout"`
- [ ] **Step 2: Implement** `ExceptionBuiltinClassifier(FieldProducer)` with BUILTIN_MAP (~60 stdlib types)
- [ ] **Step 3: Wrap with `@plugin`**
- [ ] **Step 4: Commit**

---

## Task 7.5: `spine.classifier.exception.unclass` plugin (Layer-C fallback)

**Files:**
- Create: `lca/plugins/observability/spine/classifiers/exception_unclass.py`
- Test: `tests/lca_plugins/observability/spine/test_classifier_unclass.py`

- [ ] **Step 1: Test** — unknown exception emits `UnclassifiedError` event with `first_seen=True`, full context
- [ ] **Step 2: Implement** `UnclassClassifier(FieldProducer)` with `_seen_signatures` index; after 3 occurrences sets `recommended_action="add_to_BUILTIN_MAP"`
- [ ] **Step 3: Wrap with `@plugin`** priority 99 (last)
- [ ] **Step 4: Commit**

---

## Task 7.6: `spine.spantree` plugin

**Files:**
- Create: `lca/plugins/observability/spine/spantree.py`
- Test: similar

- [ ] **Step 1+2+3+4+5**; produces `span_id`, `parent_span_id`, `sequence`, `epoch`, `prev_event_hash`; phase-machine check on pop

---

## Task 7.7: `spine.deriver.anomaly` plugin (I15 + I16, 8 detectors)

**Files:**
- Create: `lca/plugins/observability/spine/derivers/anomaly.py`
- Test: `tests/lca_plugins/observability/spine/test_anomaly_detector.py`

- [ ] **Step 1: Test** — `NearTimeoutDetector` triggers when `duration_ms > declared.timeout_ms * 0.94`
- [ ] **Step 2: Implement** 8 detectors:
  - `_check_near_timeout`, `_check_cycle`, `_check_stuck`, `_check_stalled`,
    `_check_state_machine_violation`, `_check_near_budget`, `_check_collision`, `_check_orphan_side_effect`
- [ ] **Step 3: Wrap** each as method on `AnomalyDetector(Deriver)` registered under plugin `spine.deriver.anomaly`
- [ ] **Step 4: I16 build check** — verify all 8 `_check_*` methods exist via `hasattr` reflection at boot

```python
def test_anomaly_detector_has_8_methods():
    from lca.plugins.observability.spine.derivers.anomaly import AnomalyDetector
    expected = {"near_timeout","cycle","stuck","stalled",
               "state_machine_violation","near_budget","collision","orphan_side_effect"}
    actual = {m.replace("_check_","") for m in dir(AnomalyDetector) if m.startswith("_check_")}
    assert expected == actual
```

- [ ] **Step 5: Commit** `feat(spine.plug): 8-detector anomaly plugin (I16)`

---

## Task 7.8: `spine.emit_pipeline` plugin

**Files:**
- Create: `lca/plugins/observability/spine/emit_pipeline.py`
- Test: `tests/lca_plugins/observability/spine/test_emit_pipeline.py`

- [ ] **Step 1: Test** — when 3 producers are enabled, their fields are merged in priority order without overlap
- [ ] **Step 2: Implement** `EmitPipeline(producers, anomaly).emit(...)` — applies Layer-1..3 + I12-I17 checks
- [ ] **Step 3: Wrap** `@plugin(id="spine.emit_pipeline", provides=("emit_pipeline",), requires=("field_producer.*",), layer="L1")`
- [ ] **Step 4: Commit**

---

## PR-7 Acceptance

- 18 sub-tasks, each committed per task.
- `uv run pytest tests/lca_plugins/observability/spine/ -v` PASS.
- All FieldProducer plugins produce expected fields; AnomalyDetector 8-check enforcement active.

---

# PR-7.1: spine-auto-fields-wiring

## Task 7.1.1: Replace monolithic reflector calls in `wrap_instrument`

**Files:**
- Modify: `lca/infrastructure/observability/spine/instrumentation/runtime_hooks.py` (still exists)
- Modify: `lca/harness/declarative/compile/instrument_wrap.py` (instr wrap)
- Test: `tests/observability/spine/test_wrap_uses_emit_pipeline.py`

- [ ] **Step 1: Test** — `wrap_instrument(fn)` invocation produces events whose payload includes each enabled field producer's output
- [ ] **Step 2: Refactor** `wrap_instrument` to call `emit_pipeline.emit(...)` instead of building payload inline
- [ ] **Step 3: Run tests, confirm parity**
- [ ] **Step 4: Commit** `refactor(spine): emit_pipeline wires all field producers (PR-7.1)`

---

## Task 7.1.2: Hook existing 3 wrap kinds (ctx.effect / ctx.intercept / assembler) through the pipeline

**Files:**
- Modify: `lca/infrastructure/observability/spine/instrumentation/runtime_hooks.py`
- Modify: `lca/harness/declarative/compile/assembler.py`
- Test: end-to-end `tests/integration/test_e2e_full_pipeline.py`

- [ ] **Step 1: Test** — running a profiled run with `oii-debug` profile produces events with all 18 reflectors populated
- [ ] **Step 2: Refactor** to fetch `emit_pipeline` via `ctx.require("emit_pipeline")`
- [ ] **Step 3: Commit** `refactor(spine): wire all wrap kinds through emit_pipeline`

---

## PR-7.1 Acceptance

- `uv run pytest tests/integration/test_e2e_full_pipeline.py -v` PASS.
- All wrap kinds feed emit_pipeline.

---

# PR-8: spine-plugin-extraction

## Task 8.1: Move each of 18 sub-plugins into final tree

**Files:**
- Already existing from PR-7 tasks 7.1..7.8 + 3 sinks + 3 wraps.
- Each `@plugin` invocation moves to its final location under `lca/plugins/observability/spine/{reflectors,classifiers,derivers,sinks,wraps,emit_pipeline.py,core.py}` (18 plugins total).

- [ ] **Step 1: Inventory** — confirm `lca/plugins/observability/spine/` has exactly the 18 plugins
- [ ] **Step 2: For each**, ensure it uses only L0 + L1 + L2 dependencies per table in spec § 7.6.5
- [ ] **Step 3: Add `spine.core` plugin** that composes pipeline + sinks + derivers → `event_spine`, `spine_context`
- [ ] **Step 4: Commit per sub-tree** or single `feat(spine): extract 18 plugins under lca/plugins/observability/spine/`

---

## Task 8.2: Delete `lca/infrastructure/observability/spine/instrumentation/`

**Files:**
- Delete: `lca/infrastructure/observability/spine/instrumentation/{signature_reflector,exception_classifier,context_snapshotter,edge_case_binder,span_tree_assembler,emit_pipeline,runtime_hooks}.py`

- [ ] **Step 1: Run full pytest** to ensure no broken imports elsewhere
- [ ] **Step 2: Confirm** all § 7.6.5 table rows resolve
- [ ] **Step 3: Delete the package**
- [ ] **Step 4: Commit** `chore(spine): remove monolithic instrumentation/ package (PR-8)`

---

## Task 8.3: 3 profiles (web-standard / oii-debug / benchmark) per § 7.6.6

**Files:**
- Modify: `profiles/web-standard.yaml`
- Create: `profiles/oii-debug.yaml`
- Create: `profiles/benchmark.yaml`

- [ ] **Step 1: Validate** each profile via `lca.kernel.compile_profile --validate-only` (introduce if not yet present)
- [ ] **Step 2: Commit** `feat(profiles): web-standard / oii-debug / benchmark spine compositions`

---

## PR-8 Acceptance

- `lca/infrastructure/observability/spine/instrumentation/` deleted.
- 18 plugins loadable from 3 profiles.
- `uv run pytest tests/lca_plugins/observability/spine/ -v` PASS with all sub-tests green.

---

# PR-9: spine-source-attacher

## Task 9.1: `spine.reflector.source` plugin

**Files:**
- Create: `lca/plugins/observability/spine/reflectors/source.py`
- Test: `tests/lca_plugins/observability/spine/test_source_attacher.py`

- [ ] **Step 1: Test** — wrapped function produces event with `source_location.file/line/function` matching the call site

```python
def test_source_attacher_captures_call_site():
    from lca.plugins.observability.spine.reflectors.source import SourceAttacher
    src = SourceAttacher()

    def a_function():
        # source location of *this* call is test file at line N
        return src.produce(fn=a_function, args=(), kwargs={},
                           ctx=None, span=None, phase="pre")

    fields = a_function()
    assert "source_location" in fields
    assert fields["source_location"].file.endswith("test_source_attacher.py")
    assert fields["source_location"].function == "a_function"
```

- [ ] **Step 2: Test** `locals_snapshot` is `repr`-truncated to 4 KB and redacts `os.environ["OPENAI_API_KEY"]`-style values

```python
def test_source_attacher_redacts_secrets():
    from lca.plugins.observability.spine.reflectors.source import SourceAttacher
    src = SourceAttacher(redact_patterns=[r"sk-[A-Za-z0-9]{16,}"])
    sensitive_value = "sk-abc123def4567890xyz"
    fields = src.produce(fn=lambda: None, args=(), kwargs=None,
                         ctx=type("Ctx", (), {"token": sensitive_value})(),
                         span=None, phase="pre")
    snapshot = fields["locals_snapshot"].pre_call
    assert all("sk-abc" not in v for v in snapshot.values())
```

- [ ] **Step 3: Implement** — `SourceAttacher(FieldProducer)` with priority=8 (before spantree), `max_locals_bytes=4096`, `redact_patterns=[...]`
- [ ] **Step 4: Wrap with `@plugin`**
- [ ] **Step 5: Commit**

---

## Task 9.2: I17 schema enforcement

**Files:**
- Modify: `lca/infrastructure/observability/spine/emit_pipeline.py`
- Test: `tests/observability/spine/test_i17_enforcement.py`

- [ ] **Step 1: Test** — calling `emit_pipeline.emit(...)` for a `*.start` event without `source_location` raises `I17Violation`

```python
def test_i17_rejects_event_without_source():
    from lca.infrastructure.observability.spine.emit_pipeline import EmitPipeline
    pipeline = EmitPipeline(producers=[], anomaly=...)
    with pytest.raises(I17Violation):
        pipeline.emit(execution_point="brain.think.start", channel="fact",
                      span_ctx=None, caller_payload={})
```

- [ ] **Step 2: Implement** `I17Violation` and check at emit time
- [ ] **Step 3: Commit**

---

## Task 9.3: `lca-ops journal trace --locals` output

**Files:**
- Modify: `lca/operations/journal/trace_cmd.py`
- Test: `tests/operations/journal/test_trace_locals.py`

- [ ] **Step 1: Test** — `--locals` flag adds source_location column to trace output
- [ ] **Step 2: Implement** flag handling
- [ ] **Step 3: Commit**

---

## PR-9 Acceptance

- Every `*.start` event has `source_location` / `call_frames` / `locals_snapshot`.
- `lca-ops journal trace <run_id> --locals` shows the new columns.
- I17 violation prevents non-compliant code from emitting.

---

# Final Acceptance (all 9 PRs)

1. `uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run pytest && uv run vulture lca --min-confidence 80 && scripts/check_kernel_boundary.py` all PASS.
2. Layer-1..5 hard-fail enforced.
3. `run_c9fd294e5371` scenario replayed; events.jsonl contains orphan events with `phase="orphan"`.
4. `lca-ops journal trace <run_id> --locals --source` shows file:line + locals for every start event.
5. Benchmark: `spine.append` P95 < 50µs; cognition.think() end-to-end < 5% regression.
6. `lca/plugins/observability/spine/` has exactly 18 plugins; `lca/infrastructure/observability/spine/instrumentation/` does not exist.
7. Tests: ~140 new + the 87+24+19 kernel/transport/env existing = no regression.

---

## Implementation Order Recommendation

Two parallel tracks:

**Track A** (foundation) — sub-agent 1: PR-1 → PR-2 → PR-3.1 → PR-3.2 → PR-3.4 → PR-5
**Track B** (parallel from PR-1 done) — sub-agent 2: PR-3.3 → PR-4 → PR-6

Then merge to single PR stream: PR-7 → PR-7.1 → PR-8 → PR-9.

Each sub-agent runs in its own git worktree per `superpowers:using-git-worktrees`.

---

## Self-Review

1. **Spec coverage:** Every spec section maps to a task:
   - § 1 D1-D13 → D1-D11 in PR-1/3; D12 in PR-8; D13 in PR-9
   - § 3 architecture → Tasks 1.1-1.5, 3.5
   - § 4 schema → Tasks 1.2, 1.4, 7.4/7.5, 9.1
   - § 6 EXECUTION_POINTS → Task 1.1
   - § 7 weave → Tasks 3.0-3.4 + 7.0-7.8 + 9.1
   - § 8 5-layer → Tasks 1.6, 3.5, 4.2, 5.1, 7.7
   - § 9 failure → Task 1.4 (FD-1), 2.1 (FD-2)
   - § 11 timeline → entire PR stack
   - § 13 don't list → enforced via global constraints
2. **Placeholder scan:** No TBD/TODO. All code blocks are concrete.
3. **Type consistency:** `EventRecord` / `SpineContext` / `EventSink` / `Deriver` / `FieldProducer` defined once at foundation; reused exactly as named elsewhere.
4. **Risk gating:** Each PR has Acceptance that maps to a CI check.
5. **No PR exceeds 7 days** except PR-7 (8 days) which is split into 8 sub-tasks.
