"""Regression: finalize-time artifact-closure StepTextDelta must carry scope.

Bug introduced in 164b58011 (2026-08-21 00:54:48 +0800):
    chore: local sweep (gateway/observability/spawn + tests + cordis/cosmokit vendored)

The commit changed ``gateway/runs/execute.py::_emit_artifact_closure_if_needed``
from::

    hub.store.append(StepTextDelta(step=-1, ...))

to::

    store = _journal_store(hub)
    store.append(StepTextDelta(step=-1, ...))

The new helper returns a raw ``RunStore`` whose ``append()`` reads
``get_current_run_scope()`` from a ContextVar. ``finalize()`` is invoked from
``execute_run()``'s ``finally:`` block — *after* ``with run_scope():`` has
already exited, so the ContextVar is empty. Observed in trace
``run_a34f8bd15db6`` seq 637 (the very last journal entry before the
AgentRunFinished stream closed)::

    scope: {"trace_id": "", "run_id": "", "agent_role": "", "step": 0},
    event_type: "StepTextDelta",
    data: {"step": -1, "channel": "answer",
           "text_delta": "\\n\\n已生成以下文件：\\n- [📥 ..."}

The lobe-chat SSE consumer dropped this event because ``trace_id`` /
``run_id`` were empty — the ``已生成以下文件`` + file-link tail never
rendered to the user.

Fix (executed in this PR): wrap ``_emit_artifact_closure_if_needed`` inside
``finalize()`` with ``with run_scope(RunScope(trace_id=..., run_id=...))``
so the ContextVar is populated for the emit.

These tests assert the invariant: when ``finalize()`` is invoked with a
session that has harvested artifacts, the resulting journal contains a
``StepTextDelta`` whose ``scope.trace_id`` and ``scope.run_id`` match the
session.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from gateway.runs.execute import finalize
from gateway.runs.live import LiveTail
from gateway.runs.session import RunRegistry, RunSession, RunStatus
from lca.contracts.atoms.enums import StreamChannel
from lca.harness.observability import make_minimal_bound
from lca.layer0_infra.observability.journal_backend import MemoryJournal
from lca.layer0_infra.workspace.artifact_ledger import ArtifactLedger


@pytest.mark.asyncio
async def test_finalize_artifact_closure_step_text_delta_carries_scope(
    tmp_path: Path,
) -> None:
    trace_id = "trace_regression_xyz"
    run_id = "run_regression_xyz"

    # MemoryJournal backs hub; _journal_store(hub) returns its RunStore.
    journal = MemoryJournal()
    hub = make_minimal_bound(journal=journal)

    # Workspace with one harvested artifact → closure_text() is non-empty.
    workspace = SimpleNamespace(artifacts=ArtifactLedger())
    workspace.artifacts.record_file(
        name="chart.png",
        mime_type="image/png",
        url="/files/file_abc",
        size_bytes=1024,
    )
    assert workspace.artifacts.closure_text()

    # Minimal session — only the fields finalize() + the buggy emit path
    # actually read.
    session = RunSession(
        run_id=run_id,
        trace_id=trace_id,
        jsonl_path=tmp_path / "journal.jsonl",
        tail=LiveTail(),
        question="hi",
        user_text="hi",
        mode="solo",
        hub=hub,
        status=RunStatus.RUNNING,
    )

    # Registry: bypass register() (needs JSONL writer) — inject directly.
    registry = RunRegistry(runs_dir=tmp_path)
    registry._runs[run_id] = session

    # Act: finalize() must emit a scope-bearing StepTextDelta before any
    # potential error in finalize_run / _record_doctor / _dispose_export.
    await finalize(session, registry, workspace, success=True)

    # Assert: exactly one StepTextDelta, scope bound to this run.
    events = journal.store.events
    step_text_deltas = [e for e in events if e.event_type == "StepTextDelta"]
    assert len(step_text_deltas) == 1, (
        f"expected exactly one StepTextDelta, got {len(step_text_deltas)}: "
        f"{[e.event_type for e in events]}"
    )

    stamped = step_text_deltas[0]
    assert stamped.scope.trace_id == trace_id, (
        f"scope.trace_id must equal session.trace_id; got {stamped.scope.trace_id!r}"
    )
    assert stamped.scope.run_id == run_id, (
        f"scope.run_id must equal session.run_id; got {stamped.scope.run_id!r}"
    )

    # Tail content sanity — this is the "已生成以下文件" line the user
    # lost before the fix.
    delta = stamped.event
    assert delta.channel == StreamChannel.ANSWER.value
    assert "已生成以下文件" in delta.text_delta
    assert "/files/file_abc" in delta.text_delta


@pytest.mark.asyncio
async def test_finalize_without_artifact_skips_closure_emit(
    tmp_path: Path,
) -> None:
    """No harvested artifact → no closure StepTextDelta. Negative control."""
    journal = MemoryJournal()
    hub = make_minimal_bound(journal=journal)
    workspace = SimpleNamespace(artifacts=ArtifactLedger())  # empty

    session = RunSession(
        run_id="run_empty",
        trace_id="trace_empty",
        jsonl_path=tmp_path / "journal.jsonl",
        tail=LiveTail(),
        question="hi",
        user_text="hi",
        mode="solo",
        hub=hub,
        status=RunStatus.RUNNING,
    )
    registry = RunRegistry(runs_dir=tmp_path)
    registry._runs["run_empty"] = session

    await finalize(session, registry, workspace, success=True)

    step_text_deltas = [e for e in journal.store.events if e.event_type == "StepTextDelta"]
    assert step_text_deltas == []
