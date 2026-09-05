"""PR-3h Session.append 兼容 shim 单测(ADR-0186 收口)。

ADR-0186 后 ``spine_port_append`` 只转发给 Session hook;无 hook 绑定时
RuntimeError fail-loud。同步直写路径已删除。

- 钩子已绑定:``append_via_session`` / ``append`` 均转发写入,钩子返回的
  record 原样回传;
- 钩子未绑定:RuntimeError fail-loud;
- 钩子抛错:log + 重新抛出(不返回 stub record)。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from lca.infrastructure.observability.loop_cursor._spine_port import (
    bind_session_append_hook,
    reset_session_append_hook,
    _session_append_hook,
)
from lca.infrastructure.observability.spine.context import SpineContext
from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.event_spine import EventSpine
from lca.infrastructure.observability.spine.sinks.base import EventSink
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink


def _stub_record(execution_point: str) -> EventRecord:
    now = datetime.now(timezone.utc)
    return EventRecord(
        execution_point=execution_point,
        channel="fact",
        span_id="session-stub-span",
        parent_span_id=None,
        sequence=1,
        epoch=1,
        causality_id="sha256:session-stub",
        outcome=None,
        when=now,
        when_corrected=now,
        prev_event_hash=None,
        run_id="session-stub-run",
        step_id=None,
        payload={"via": "session-stub"},
    )


class _ForwardRecorder:
    """桩 Session runtime:记录转发入参,返回桩 record,不落盘。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        sinks: Sequence[EventSink],
        subscribers: Sequence[Callable[[EventRecord], None]],
        *,
        execution_point: str,
        **kwargs: Any,
    ) -> EventRecord:
        self.calls.append({"execution_point": execution_point, **kwargs})
        return _stub_record(execution_point)


class _RaisingHook:
    """桩故障 Session runtime:转发必抛错,验证 contained 语义。"""

    def __call__(
        self,
        sinks: Sequence[EventSink],
        subscribers: Sequence[Callable[[EventRecord], None]],
        *,
        execution_point: str,
        **kwargs: Any,
    ) -> EventRecord:
        raise RuntimeError("session runtime unavailable")


def test_append_via_session_forwards_to_bound_hook(tmp_path: Path) -> None:
    """钩子绑定时写入转发给 Session runtime;sink / subscribers 不触发。"""
    SpineContext.set_run("r-session-forward")
    sink = FileSink(tmp_path, run_id="r-session-forward")
    seen: list[EventRecord] = []
    spine = EventSpine(sinks=[sink], subscribers=[seen.append])
    hook = _ForwardRecorder()
    token = bind_session_append_hook(hook)
    try:
        rec = spine.append_via_session(
            execution_point="brain.think.start",
            channel="fact",
            caller_payload={"via": "session"},
        )
    finally:
        reset_session_append_hook(token)
        spine.close()

    assert len(hook.calls) == 1
    assert hook.calls[0]["execution_point"] == "brain.think.start"
    assert hook.calls[0]["caller_payload"] == {"via": "session"}
    # 钩子返回值原样回传;转发拥有写入,同步路径未触 sink / subscribers
    assert rec.payload == {"via": "session-stub"}
    assert seen == []
    ledger = tmp_path / "r-session-forward.spine.jsonl"
    assert ledger.read_text(encoding="utf-8") == ""


def test_append_via_session_runtime_error_when_no_hook(tmp_path: Path) -> None:
    """ADR-0186 收口:无钩子绑定时 RuntimeError fail-loud(同步直写路径已删除)。"""
    SpineContext.set_run("r-session-no-hook")
    sink = FileSink(tmp_path, run_id="r-session-no-hook")
    spine = EventSpine(sinks=[sink], subscribers=[])
    # Explicitly unbind the autouse hook from conftest to test no-hook behavior
    unbind_token = _session_append_hook.set(None)
    try:
        with pytest.raises(RuntimeError, match="no Session hook bound"):
            spine.append_via_session(
                execution_point="brain.think.start",
                channel="fact",
                caller_payload={"via": "fail-loud"},
            )
    finally:
        _session_append_hook.reset(unbind_token)
        spine.close()
    # sink 未写入
    ledger = tmp_path / "r-session-no-hook.spine.jsonl"
    assert not ledger.exists() or ledger.read_text(encoding="utf-8") == ""


def test_append_via_session_raising_hook_propagates(tmp_path: Path) -> None:
    """钩子抛错时 fail-loud:log + 传播,不返回 stub record。"""
    SpineContext.set_run("r-session-raising")
    sink = FileSink(tmp_path, run_id="r-session-raising")
    spine = EventSpine(sinks=[sink], subscribers=[])
    token = bind_session_append_hook(_RaisingHook())
    try:
        with pytest.raises(RuntimeError, match="session runtime unavailable"):
            spine.append_via_session(
                execution_point="brain.think.start",
                channel="fact",
                caller_payload={"via": "contained"},
            )
    finally:
        reset_session_append_hook(token)
        spine.close()


# ── ADR-0186 PR-3h: EventSpine.append 自动优先 Session ────────────────────


def test_append_prefers_session_hook_when_bound(tmp_path: Path) -> None:
    """ADR-0186: ``EventSpine.append`` 在钩子绑定时自动走 Session 路径。"""
    SpineContext.set_run("r-append-prefers-session")
    sink = FileSink(tmp_path, run_id="r-append-prefers-session")
    seen: list[EventRecord] = []
    spine = EventSpine(sinks=[sink], subscribers=[seen.append])
    hook = _ForwardRecorder()
    token = bind_session_append_hook(hook)
    try:
        rec = spine.append(
            execution_point="brain.think.start",
            channel="fact",
            caller_payload={"via": "append-session"},
        )
    finally:
        reset_session_append_hook(token)
        spine.close()

    assert len(hook.calls) == 1
    assert hook.calls[0]["execution_point"] == "brain.think.start"
    assert hook.calls[0]["caller_payload"] == {"via": "append-session"}
    assert rec.payload == {"via": "session-stub"}
    assert seen == []


def test_append_runtime_error_when_no_hook(tmp_path: Path) -> None:
    """ADR-0186 收口:无钩子绑定时 ``EventSpine.append`` RuntimeError。"""
    SpineContext.set_run("r-append-no-hook")
    sink = FileSink(tmp_path, run_id="r-append-no-hook")
    spine = EventSpine(sinks=[sink], subscribers=[])
    # Explicitly unbind the autouse hook from conftest to test no-hook behavior
    unbind_token = _session_append_hook.set(None)
    try:
        with pytest.raises(RuntimeError, match="no Session hook bound"):
            spine.append(
                execution_point="brain.think.start",
                channel="fact",
                caller_payload={"via": "fail-loud"},
            )
    finally:
        _session_append_hook.reset(unbind_token)
        spine.close()
