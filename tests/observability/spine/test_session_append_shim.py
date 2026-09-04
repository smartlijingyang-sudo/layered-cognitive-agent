"""PR-3h Session.append 兼容 shim 单测(骨架)。

骨架期无真实 Session runtime;转发缝由桩钩子钉死:

- 钩子已绑定:``append_via_session`` / ``append`` 均转发写入,钩子返回的
  record 原样回传,同步直写路径不触发(不触 sink、不通知 subscribers);
- 钩子未绑定 / 转发抛错:落回原同步直写路径,落盘与 subscriber 语义与
  :meth:`EventSpine.append` 一致。

ADR-0186 PR-3h 起 ``spine_port_append`` 自动读取 ContextVar,``EventSpine.append``
与 ``append_via_session`` 行为等价(均优先 Session)。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from lca.infrastructure.observability.loop_cursor._spine_port import (
    bind_session_append_hook,
    reset_session_append_hook,
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
    """桩故障 Session runtime:转发必抛错,验证容错落回同步路径。"""

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
    """钩子绑定时写入转发给 Session runtime;同步直写路径不触发。"""
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


@pytest.mark.parametrize("hook_kind", ["none", "raising"])
def test_append_via_session_falls_back_to_sync_path(tmp_path: Path, hook_kind: str) -> None:
    """无钩子 / 钩子抛错:落回原同步直写路径,落盘与 subscriber 语义不变。"""
    SpineContext.set_run("r-session-fallback")
    sink = FileSink(tmp_path, run_id="r-session-fallback")
    seen: list[EventRecord] = []
    spine = EventSpine(sinks=[sink], subscribers=[seen.append])
    token = bind_session_append_hook(_RaisingHook()) if hook_kind == "raising" else None
    try:
        rec = spine.append_via_session(
            execution_point="brain.think.start",
            channel="fact",
            caller_payload={"via": "fallback"},
        )
    finally:
        if token is not None:
            reset_session_append_hook(token)
        spine.close()

    assert rec.run_id == "r-session-fallback"
    assert rec.sequence >= 1
    assert len(seen) == 1
    lines = (tmp_path / "r-session-fallback.spine.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["execution_point"] == "brain.think.start"
    assert obj["payload"] == {"via": "fallback"}


# ── ADR-0186 PR-3h: EventSpine.append 自动优先 Session ────────────────────


def test_append_prefers_session_hook_when_bound(tmp_path: Path) -> None:
    """ADR-0186 PR-3h: ``EventSpine.append`` 在钩子绑定时自动走 Session 路径。

    ``spine_port_append`` 自动读取 ContextVar,调用方无需显式传 hook。
    """
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
    # 钩子返回值原样回传;同步路径未触 sink / subscribers
    assert rec.payload == {"via": "session-stub"}
    assert seen == []
    ledger = tmp_path / "r-append-prefers-session.spine.jsonl"
    assert ledger.read_text(encoding="utf-8") == ""


def test_append_falls_back_when_no_hook(tmp_path: Path) -> None:
    """ADR-0186 PR-3h: 无钩子绑定时 ``EventSpine.append`` 走同步直写路径(行为不变)。"""
    SpineContext.set_run("r-append-no-hook")
    sink = FileSink(tmp_path, run_id="r-append-no-hook")
    seen: list[EventRecord] = []
    spine = EventSpine(sinks=[sink], subscribers=[seen.append])
    try:
        rec = spine.append(
            execution_point="brain.think.start",
            channel="fact",
            caller_payload={"via": "sync-path"},
        )
    finally:
        spine.close()

    assert rec.run_id == "r-append-no-hook"
    assert rec.sequence >= 1
    assert len(seen) == 1
    lines = (tmp_path / "r-append-no-hook.spine.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["execution_point"] == "brain.think.start"
    assert obj["payload"] == {"via": "sync-path"}
