"""Regression tests for PR-1 narrow wrappers (cursor second-track → Session.append).

delete-when: the two narrow wrappers
``lca.loop.commit.tool_journal.record_step_tool_call`` /
``record_step_tool_result`` are the only business-path entry for the
``step.tool_call.record`` / ``step.tool_result.record`` spine EPs.
This file locks the migration contract: payload shape, idempotency
boundary, ok/outcome contradiction guard.

ADR-0186 §3.4 (single track) · ADR-0192 §3.1 (FactCommitter terminal) ·
ADR-0195 §2.3 (four-segment chain Gateway stage).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from lca.loop.commit.tool_journal import (
    record_step_tool_call,
    record_step_tool_result,
)


def _capture_publish_ep() -> dict[str, Any]:
    """Return a dict that ``patch`` populates with the published payload."""
    return {}


def test_record_step_tool_call_publishes_step_tool_call_record_ep() -> None:
    captured: list[tuple[str, dict[str, Any]]] = []

    def fake_publish_ep(
        ep: str,
        payload: dict[str, Any],
        *,
        state: Any = None,
        session: Any = None,
        actor: str = "body",
    ) -> None:
        captured.append((ep, dict(payload)))

    with patch(
        "lca.loop.commit.tool_journal.publish_ep_bound",
        side_effect=fake_publish_ep,
    ):
        record_step_tool_call(
            tool_name="test_tool",
            invocation_id="inv-1",
            arguments={"x": 1, "y": "two"},
            arguments_summary="x=1, y='two'",
        )

    assert len(captured) == 1
    ep, payload = captured[0]
    assert ep == "step.tool_call.record"
    # business payload fields (binding rule: payload.tool_name|payload.name)
    assert payload["tool_name"] == "test_tool"
    assert payload["invocation_id"] == "inv-1"
    assert payload["arguments"] == {"x": 1, "y": "two"}
    assert payload["arguments_summary"] == "x=1, y='two'"
    # no deprecated digest field on the wire
    assert "args_digest" not in payload
    # step / run_id always present (carried by _phase_tool_context, may be empty
    # outside a run scope — that is fine, just ensure no KeyError)
    assert "step" in payload
    assert "run_id" in payload


def test_record_step_tool_call_with_no_arguments_omits_field() -> None:
    captured: list[dict[str, Any]] = []

    def fake_publish_ep(
        ep: str,
        payload: dict[str, Any],
        *,
        state: Any = None,
        session: Any = None,
        actor: str = "body",
    ) -> None:
        captured.append(dict(payload))

    with patch(
        "lca.loop.commit.tool_journal.publish_ep_bound",
        side_effect=fake_publish_ep,
    ):
        record_step_tool_call(
            tool_name="test_tool",
            invocation_id="inv-2",
            arguments=None,
        )

    assert captured[0]["arguments"] is None  # type: ignore[index]
    # summary absent when not supplied
    assert "arguments_summary" not in captured[0]


def test_record_step_tool_result_publishes_step_tool_result_record_ep() -> None:
    captured: list[tuple[str, dict[str, Any]]] = []

    def fake_publish_ep(
        ep: str,
        payload: dict[str, Any],
        *,
        state: Any = None,
        session: Any = None,
        actor: str = "body",
    ) -> None:
        captured.append((ep, dict(payload)))

    with patch(
        "lca.loop.commit.tool_journal.publish_ep_bound",
        side_effect=fake_publish_ep,
    ):
        record_step_tool_result(
            tool_name="test_tool",
            invocation_id="inv-3",
            outcome="ok",
            ok=True,
            latency_ms=42,
            stdout_head="hello\nworld",
            stdout_chars_total=11,
            stdout_truncated=False,
            stderr="",
            files_created=("out.txt",),
            error=None,
            delta_summary="✅ ok",
        )

    assert len(captured) == 1
    ep, payload = captured[0]
    assert ep == "step.tool_result.record"
    # every field in the binding rule (journal_step_tree.yaml: tool_result_evidence)
    assert payload["tool_name"] == "test_tool"
    assert payload["invocation_id"] == "inv-3"
    assert payload["outcome"] == "ok"
    assert payload["ok"] is True
    assert payload["latency_ms"] == 42
    assert payload["stdout_head"] == "hello\nworld"
    assert payload["stdout_chars_total"] == 11
    assert payload["stdout_truncated"] is False
    assert payload["files_created"] == ["out.txt"]
    assert payload["delta_summary"] == "✅ ok"
    # stderr omitted when empty (no false-positive fields)
    assert "stderr" not in payload
    assert "error" not in payload  # None → omitted


def test_record_step_tool_result_rejects_ok_outcome_contradiction() -> None:
    """outcome='ok' with ok=False is rejected before reaching the bus.

    Mirrors ``FoldConsistencyError`` (binding_engine.apply_tool_result): the
    upstream emitter must refuse, otherwise a contradiction reaches the journal.
    """
    with (
        patch("lca.loop.commit.tool_journal.publish_ep_bound") as publish,
        pytest.raises(ValueError, match="outcome='ok' requires ok=True"),
    ):
        record_step_tool_result(
            tool_name="test_tool",
            invocation_id="inv-bad-1",
            outcome="ok",
            ok=False,
        )
    publish.assert_not_called()


def test_record_step_tool_result_rejects_failure_outcome_with_ok_true() -> None:
    """outcome='failure'/'timeout'/'denied' with ok=True is also rejected."""
    for outcome in ("failure", "timeout", "denied"):
        with (
            patch("lca.loop.commit.tool_journal.publish_ep_bound") as publish,
            pytest.raises(ValueError, match=f"outcome={outcome!r} requires ok=False"),
        ):
            record_step_tool_result(
                tool_name="test_tool",
                invocation_id="inv-bad-2",
                outcome=outcome,  # type: ignore[arg-type]
                ok=True,
            )
        publish.assert_not_called()


def test_summarize_args_consolidates_two_prior_copies() -> None:
    """Both former private copies were consolidated to summarize_args.

    Locks the public surface so a future copy cannot re-emerge as a
    shadow helper (report_digest_inconsistency.md finding).
    """
    from lca.cognition.body.emit._args_summary import summarize_args

    assert summarize_args({"a": 1, "b": "two", "c": [1, 2, 3]}) == "a=1, b='two', c=[1, 2, 3]"
    assert summarize_args({}) == ""
    # Truncation: more than 5 keys → only first 5
    sample = {f"k{i}": i for i in range(10)}
    out = summarize_args(sample)
    assert out.startswith("k0=0, k1=1, k2=2, k3=3, k4=4")
    assert len(out) <= 201


def test_business_path_no_longer_imports_cursor_record() -> None:
    """Grep-style guard encoded as a test: business modules must not import CursorRecord.

    delete-when: the second-track is fully retired (ADR-0185 P5).
    """
    import lca.cognition.body.emit.tool_journal as tj_mod
    import lca.cognition.body.executor.pipeline_safe_executor as pipe_mod
    import lca.cognition.body.executor.safe_executor as safe_mod

    assert not hasattr(safe_mod, "CursorRecord"), (
        "safe_executor must not re-export CursorRecord — single track via Session.append"
    )
    assert not hasattr(pipe_mod, "CursorRecord"), (
        "pipeline_safe_executor must not re-export CursorRecord"
    )
    assert not hasattr(tj_mod, "CursorRecord"), (
        "tool_journal must not re-export CursorRecord"
    )
