"""Regression: step-tool-result file metadata must be string paths, not dicts.

ADR-0164 step-tree introduced ``bridge_tool_invoked(files_created=...)`` and
``narrative_writer._render_context`` reading ``ctx.cumulative_files``. Both
consumers call ``Path(f).name`` on each element. ``tool_files(obs)`` returns
A2A file-part dicts (with ``name`` / ``mimeType`` / ``url`` keys). If those
dicts leak into ``ToolResult.files_created`` instead of the names, the
renderer raises ``TypeError: argument should be a str or an os.PathLike
object where __fspath__ returns a str, not 'dict'`` (reproduced on
2026-09-01 run_ccc9393cdbd1 — narrative writer / step-tree flusher crashed
mid-terminalize, journal.jsonl never landed).

These tests pin the contract: ``files_created`` is ``tuple[str, ...]`` of
display names, and the human-readable ``delta_summary`` keeps using names.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from lca.contracts.models.observability import JournalMetadata
from lca.infrastructure.observability import facade as fd
from lca.infrastructure.observability.facade.facade import (
    _run_context as _run_ctx_var,
)
from lca.runtime import step_emitter, step_lifecycle

# ── fixtures ───────────────────────────────────────────────────────────


class _Tool:
    name = "write-file"


class _FileObs:
    """Observation carrying A2A file parts in ``extra.files``."""

    success: ClassVar[bool] = True
    error: ClassVar[str] = ""
    extra: ClassVar[dict[str, Any]] = {
        "files": [
            {
                "name": "订单宝V1.0_倒排任务表.xlsx",
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "sizeBytes": 24129,
                "url": "/files/file_8e4bf89067d3",
                "attachmentId": "file_8e4bf89067d3",
            },
            {
                "name": "summary.md",
                "mimeType": "text/markdown",
                "sizeBytes": 4096,
                "url": "/files/file_summary",
                "attachmentId": "file_summary",
            },
        ]
    }
    payload: ClassVar[dict[str, Any]] = {}


@pytest.fixture
def bound_store() -> object:
    """Bind a fresh lifecycle store + run context for the test."""
    store = step_lifecycle.StepLifecycleStore()
    store.bind_run(
        run_id="r_files_regression",
        trace_id="t_files_regression",
        metadata=JournalMetadata(
            agent_role="agt_test",
            strategy_key="solo",
            plan_ref="plan_files_regression",
            objective="write files",
        ),
    )
    store_token = step_lifecycle.set_lifecycle_store(store)
    ctx_token = _run_ctx_var.set(
        fd.RunContext(run_id="r_files_regression", trace_id="t_files_regression")
    )
    try:
        yield store
    finally:
        _run_ctx_var.reset(ctx_token)
        step_lifecycle.reset_lifecycle_store(store_token)


# ── tests ─────────────────────────────────────────────────────────────


def test_files_created_is_strings_not_dicts(bound_store: object) -> None:
    """``bridge_tool_invoked`` must receive names, not file-part dicts."""
    from lca.cognition.body.tool_journal_emit import emit_tool_invoked

    step_emitter.bridge_act_opened(objective="act", tool_name="write-file")
    emit_tool_invoked(
        _Tool(),
        {},
        _FileObs(),  # type: ignore[arg-type]
        latency_ms=10,
        attempt=1,
        invocation_id="inv_files_regression",
    )
    step_emitter.bridge_act_closed(outcome="ok", summary="done")

    closed = bound_store.get_closed_steps()
    act_step = next(s for s in closed if s.phase == "act")
    files_created = act_step.tool_result.files_created

    # core invariant — no dicts leak through
    assert files_created, "files_created should be populated when extra.files carries dicts"
    assert all(isinstance(name, str) for name in files_created), (
        f"files_created must be tuple[str, ...], got {[type(n).__name__ for n in files_created]}"
    )
    assert files_created == (
        "订单宝V1.0_倒排任务表.xlsx",
        "summary.md",
    )


def test_cumulative_files_is_strings(bound_store: object) -> None:
    """``JournalDocument.cumulative_files`` must aggregate strings, not dicts."""
    from lca.cognition.body.tool_journal_emit import emit_tool_invoked

    step_emitter.bridge_act_opened(objective="act", tool_name="write-file")
    emit_tool_invoked(
        _Tool(),
        {},
        _FileObs(),  # type: ignore[arg-type]
        latency_ms=10,
        attempt=1,
        invocation_id="inv_files_regression",
    )
    step_emitter.bridge_act_closed(outcome="ok", summary="done")

    doc = fd.step_close_document(outcome="completed")
    assert doc is not None
    cum = doc.cumulative_files()
    assert all(isinstance(name, str) for name in cum)
    assert cum == ("订单宝V1.0_倒排任务表.xlsx", "summary.md")


def test_narrative_writer_renders_cumulative_files(bound_store: object, tmp_path) -> None:
    """``StepNarrativeWriter`` must not raise ``TypeError`` when files_created is populated."""
    from lca.cognition.body.tool_journal_emit import emit_tool_invoked

    step_emitter.bridge_act_opened(objective="act", tool_name="write-file")
    emit_tool_invoked(
        _Tool(),
        {},
        _FileObs(),  # type: ignore[arg-type]
        latency_ms=10,
        attempt=1,
        invocation_id="inv_files_regression",
    )
    step_emitter.bridge_act_closed(outcome="ok", summary="done")

    doc = fd.step_close_document(outcome="completed")
    assert doc is not None

    from lca.infrastructure.observability.journal.step.narrative_writer import (
        StepNarrativeWriter,
    )

    out = tmp_path / "narrative.md"
    writer = StepNarrativeWriter(out)
    # before the fix, this raised:
    #   TypeError: argument should be a str or an os.PathLike object
    #   where __fspath__ returns a str, not 'dict'
    writer.write(doc)
    assert out.exists()


def test_delta_summary_uses_names_not_paths() -> None:
    """``_delta_summary_from_obs`` must use file ``name``, never ``Path(dict)``."""
    from lca.cognition.body.tool_journal_emit import _delta_summary_from_obs

    summary = _delta_summary_from_obs(_FileObs(), "stdout text", None)  # type: ignore[arg-type]
    assert "订单宝V1.0_倒排任务表.xlsx" in summary
    assert "summary.md" in summary
    # no Path coercion of dicts, no __fspath__ traceback artefacts
    assert "{" not in summary


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
