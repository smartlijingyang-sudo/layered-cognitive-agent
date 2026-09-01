"""ADR-clean-truths: failed / canceled run 不再向 channel=answer 推产物闭合文本。

背景:run_fa054a09475f 在内部失败后,workspace 残留有"PM-...pdf"等 artifact,
LCA transport 仍向 LobeHub 推一条 StepTextDelta channel=answer 的"已生成以下文件:
.outputs / PM-...pdf" 闭合文本。LobeHub 把它当作助手答卷展示给用户,
造成 run 失败却显示"任务完成"的假成功。

修复:``emit_artifact_closure_if_needed`` 在入口读 session.status 与 session.error,
FAILED / CANCELED / session.error 非空时直接 return,绝不向 channel=answer 推文本。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from lca.contracts.atoms.enums import StreamChannel
from lca.contracts.models.observability.journal import StepTextDelta
from lca.plugins.transport.webserver.handlers.runs.observability.artifact_closure import (
    emit_artifact_closure_if_needed,
)
from lca.plugins.transport.webserver.handlers.runs.session.session import RunStatus


class _FakeStore:
    """记录 append  入的 StepTextDelta / 其他事件。"""

    def __init__(self) -> None:
        self.events: list[Any] = []

    def append(self, event: Any) -> None:
        self.events.append(event)


class _FakeJournal:
    def __init__(self) -> None:
        self.store = _FakeStore()


class _FakeHub:
    def __init__(self) -> None:
        self.journal = _FakeJournal()


class _FakeArtifactsSnapshot:
    def __init__(self) -> None:
        self.artifacts: list[Any] = [object()]  # 一个非空 artifact 列表

    def closure_text(self) -> str:
        return "已生成 PM-90571872-...pdf"


class _FakeArtifacts:
    def __init__(self) -> None:
        self._snapshot = _FakeArtifactsSnapshot()

    def snapshot(self) -> _FakeArtifactsSnapshot:
        return self._snapshot

    def closure_text(self) -> str:
        return self._snapshot.closure_text()


class _FakeWorkspace:
    def __init__(self) -> None:
        self.artifacts = _FakeArtifacts()


def _make_session(*, status: RunStatus, error: str = "") -> Any:
    return SimpleNamespace(
        run_id="run_test",
        status=status,
        error=error,
        hub=_FakeHub(),
    )


def _run_emit(session: Any) -> list[Any]:
    workspace = _FakeWorkspace()
    hub = session.hub
    emit_artifact_closure_if_needed(workspace, session, hub)
    return hub.journal.store.events


def test_failed_run_does_not_emit_answer_channel() -> None:
    """决策 二:FAILED run 即使 workspace 有产物,也不向 channel=answer 推文本。"""
    session = _make_session(status=RunStatus.FAILED)
    events = _run_emit(session)
    answer_events = [
        e
        for e in events
        if isinstance(e, StepTextDelta) and e.channel == StreamChannel.ANSWER.value
    ]
    assert answer_events == [], (
        f"FAILED run 不应向 channel=answer 推 StepTextDelta,得到 {answer_events}"
    )


def test_canceled_run_does_not_emit_answer_channel() -> None:
    """决策 二:CANCELED run 同上。"""
    session = _make_session(status=RunStatus.CANCELED)
    events = _run_emit(session)
    answer_events = [
        e
        for e in events
        if isinstance(e, StepTextDelta) and e.channel == StreamChannel.ANSWER.value
    ]
    assert answer_events == []


def test_running_run_with_session_error_does_not_emit_answer_channel() -> None:
    """决策 二:即使 status 还在 RUNNING,只要 session.error 非空就 suppress。"""
    session = _make_session(status=RunStatus.RUNNING, error="something blew up")
    events = _run_emit(session)
    answer_events = [
        e
        for e in events
        if isinstance(e, StepTextDelta) and e.channel == StreamChannel.ANSWER.value
    ]
    assert answer_events == []


def test_completed_run_still_emits_answer_channel() -> None:
    """回归保护:COMPLETED run 仍正常向 channel=answer 推产物闭合文本。"""
    session = _make_session(status=RunStatus.COMPLETED)
    events = _run_emit(session)
    answer_events = [
        e
        for e in events
        if isinstance(e, StepTextDelta) and e.channel == StreamChannel.ANSWER.value
    ]
    assert len(answer_events) == 1
    assert "PM-90571872-...pdf" in answer_events[0].text_delta


@pytest.mark.parametrize("status_value", ["failed", "canceled"])
def test_status_value_lowercase_matches_run_status_enum(status_value: str) -> None:
    """回归保护:RunStatus enum 字面量是小写("failed" / "canceled"),实现已对齐。"""
    if status_value == "failed":
        assert RunStatus.FAILED.value == "failed"
    else:
        assert RunStatus.CANCELED.value == "canceled"
