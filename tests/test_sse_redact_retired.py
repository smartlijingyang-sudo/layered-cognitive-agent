"""ADR-0101 PR-1: SSE redact mechanism is retired.

Verifies that:
- ``_LIVE_REDACT_KEYS`` is no longer importable from ``sse_frames``
- ``stamped_to_sse_frame`` has no ``redact`` parameter
- SSE frames do NOT blank out ``arguments_preview`` / ``result_preview``
  (they are absent because ``stamped_to_record`` strips view-only fields,
  not because SSE redacts them)
"""

from __future__ import annotations

import inspect
import json

import pytest

from lca.contracts.models.observability.journal import (
    RunScope,
    StampedEvent,
    ToolInvoked,
)
from lca.infrastructure.observability.journal import sse_frames
from lca.infrastructure.observability.journal.sse_frames import stamped_to_sse_frame


def _stamped(seq: int, event: object) -> StampedEvent:
    return StampedEvent(
        seq=seq,
        ts=float(seq),
        scope=RunScope(trace_id="t", run_id="r"),
        event=event,
    )


def test_live_redact_keys_not_importable() -> None:
    """_LIVE_REDACT_KEYS was removed in ADR-0101."""
    assert not hasattr(sse_frames, "_LIVE_REDACT_KEYS")


def test_stamped_to_sse_frame_has_no_redact_param() -> None:
    """stamped_to_sse_frame signature must not contain a redact parameter."""
    sig = inspect.signature(stamped_to_sse_frame)
    assert "redact" not in sig.parameters


def test_sse_frame_does_not_blank_preview_fields() -> None:
    """SSE frames must not blank out arguments_preview / result_preview.

    ADR-0101 PR-2:tool 事件 dataclass 不再有 ``arguments_preview`` /
    ``result_preview`` / typed 6-key / output_text / state_ref / plugin_state
    字段(0065 §四 L1)。SSE 帧忠实转译 v2 envelope;arguments / output 经
    ``arguments_ref`` / ``output_ref`` 走 evidence 平面。
    """
    stamped = _stamped(
        1,
        ToolInvoked(
            tool_name="executeCode",
            invocation_id="i",
            ok=True,
            latency_ms=100,
        ),
    )
    frame = stamped_to_sse_frame(stamped)
    data_line = ""
    for line in frame.splitlines():
        if line.startswith("data: "):
            data_line = line[6:]
    payload = json.loads(data_line)
    data = payload.get("data", {})
    # deprecated preview fields are absent (ADR-0101 PR-2)
    for forbidden in (
        "arguments_preview",
        "result_preview",
        "code",
        "language",
        "command",
        "skill_id",
        "skill_inputs",
        "description",
        "execution_env",
        "state_ref",
        "plugin_state",
    ):
        assert forbidden not in data, f"{forbidden} unexpectedly present in data"
    # only fact fields present
    assert data["tool_name"] == "executeCode"
    assert data["invocation_id"] == "i"
    assert data["ok"] is True
    assert data["latency_ms"] == 100
    # V7:data 包含 arguments_ref 或 arguments (二选一非空)
    assert "arguments" in data or "arguments_ref" in data


def test_stamped_to_sse_frame_accepts_no_keyword_args() -> None:
    """Passing redact=... should raise TypeError (parameter removed)."""
    stamped = _stamped(1, ToolInvoked(tool_name="t", invocation_id="i"))
    with pytest.raises(TypeError):
        stamped_to_sse_frame(stamped, redact=False)  # type: ignore[call-arg]
