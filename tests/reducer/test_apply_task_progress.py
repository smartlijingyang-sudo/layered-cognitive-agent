"""Reducer ``apply_task_progress`` invariants (ADR-0214 §3.4 / §3.6).

- completed 单调 (新 completed ⊇ 旧 completed;sorted+set 稳定)
- completed 不缩 (新 ⊂ 旧 → fold 后保持旧)
- @_instrument_apply 装饰:start / end marker 经 FactGateway emit
- 异常路径:end marker outcome='failure'
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from lca.contracts.models.core.execution.task_progress import TaskProgress
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.plugins.loop.reducer.plugin import DefaultReducer


def _make_state() -> AgentState:
    return AgentState(trace_id="t1", task="hello", budget=Budget())


class _SyntheticError(RuntimeError):
    """Local sentinel — only used to drive the failure-path test."""


def test_completed_monotonically_grows() -> None:
    """completed 单调:旧 ['a'] + 新 ['a','b'] → fold 后 ['a','b']。"""
    reducer = DefaultReducer()
    state = _make_state()
    state.task_progress = TaskProgress(completed=("a",))

    new = reducer.apply_task_progress(
        state,
        TaskProgress(completed=("a", "b"), confidence=0.5),
    )
    assert new.task_progress.completed == ("a", "b")


def test_completed_does_not_shrink_on_subset() -> None:
    """completed 不缩:旧 ['a','b'] + 新 ['a'] → fold 后保持 ['a','b']。"""
    reducer = DefaultReducer()
    state = _make_state()
    state.task_progress = TaskProgress(completed=("a", "b"))

    new = reducer.apply_task_progress(
        state,
        TaskProgress(completed=("a",)),
    )
    # 单调不变式:旧集合是并集下界;fold 后是 ['a','b']
    assert set(new.task_progress.completed) == {"a", "b"}


def test_completed_order_is_stable_after_merge() -> None:
    """completed 合并后 sorted 稳定(sort + set 保证 fold 重放一致)。"""
    reducer = DefaultReducer()
    state = _make_state()
    state.task_progress = TaskProgress(completed=("z",))

    new = reducer.apply_task_progress(
        state,
        TaskProgress(completed=("a", "m")),
    )
    # 字典序:['a', 'm', 'z']
    assert new.task_progress.completed == ("a", "m", "z")


def test_fresh_state_default_progression() -> None:
    """空 state 第一次 fold → 等于新 progress(默认 TaskProgress 是空)。"""
    reducer = DefaultReducer()
    state = _make_state()
    # state.task_progress 是默认 TaskProgress(completed=())
    new = reducer.apply_task_progress(
        state,
        TaskProgress(completed=("x",), confidence=0.3),
    )
    assert new.task_progress.completed == ("x",)
    assert new.task_progress.confidence == 0.3


def test_termination_reason_is_replaced() -> None:
    """reduction 覆盖 termination_reason(非单调)。"""
    reducer = DefaultReducer()
    state = _make_state()
    state.task_progress = TaskProgress(termination_reason=None)

    new = reducer.apply_task_progress(
        state,
        TaskProgress(termination_reason="max_steps"),
    )
    assert new.task_progress.termination_reason == "max_steps"


def test_instrument_apply_emits_start_and_end_markers() -> None:
    """@_instrument_apply 装饰:start + end marker 经 runtime emit helpers。"""
    reducer = DefaultReducer()
    state = _make_state()

    # emit_runtime_reducer_apply_* 在 reducer/plugin.py 内**懒加载**于
    # ``_publish_apply_marker`` 函数体内,因此 mock 的真实路径是它们
    # 定义的源头模块:``lca.infrastructure.session.emit.runtime_emit``。
    with (
        patch(
            "lca.infrastructure.session.emit.runtime_emit.emit_runtime_reducer_apply_start",
            return_value="start-rc",
        ) as start,
        patch(
            "lca.infrastructure.session.emit.runtime_emit.emit_runtime_reducer_apply_end",
            return_value="end-rc",
        ) as end,
    ):
        reducer.apply_task_progress(state, TaskProgress())

    assert start.call_args.kwargs == {"method": "apply_task_progress"}
    assert end.call_args.kwargs == {
        "method": "apply_task_progress",
        "outcome": "success",
    }


def test_instrument_apply_emits_failure_marker_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """@_instrument_apply:异常时仍 emit end marker outcome='failure'。"""
    reducer = DefaultReducer()
    state = _make_state()

    # 触发 reducer body 内部异常:对 ``emit_runtime_reducer_apply_start`` 的
    # mock 不抛,但 ``apply_task_progress`` body 自身 raise — 用 monkeypatch
    # 直接 patch 装饰器下的原函数是不可能的(decorator 重绑定),故此处用
    # 一个构造时抛异常的对象替代 ``TaskProgress``。
    class _ExplodingProgress:
        completed = ()
        remaining = ()
        termination_reason = None

        @property
        def confidence(self) -> float:
            raise _SyntheticError("synthetic failure")

    start_called = []
    end_called = []

    def fake_start(*, method: str):
        start_called.append(method)
        return "start-rc"

    def fake_end(*, method: str, outcome: str):
        end_called.append((method, outcome))
        return "end-rc"

    monkeypatch.setattr(
        "lca.infrastructure.session.emit.runtime_emit.emit_runtime_reducer_apply_start",
        fake_start,
    )
    monkeypatch.setattr(
        "lca.infrastructure.session.emit.runtime_emit.emit_runtime_reducer_apply_end",
        fake_end,
    )

    with pytest.raises(_SyntheticError):
        reducer.apply_task_progress(state, _ExplodingProgress())  # type: ignore[arg-type]

    assert start_called == ["apply_task_progress"]
    assert end_called == [("apply_task_progress", "failure")]
