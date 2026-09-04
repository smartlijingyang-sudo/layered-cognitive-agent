"""Fold 优化契约 5 场景单测 —— ADR-0185 §3.5。

每场景对应 fold 矩阵的一行:

| 上一状态 | 当前 header | reason | 写盘? |
|---|---|---|---|
| None | 任意 | ``initial`` | ✅ |
| 上 header | headerEquals(prev, current) == True | (不发) | ❌ |
| 上 header | headerEquals == False,system 变 | ``change`` | ✅ |
| 上 header | headerEquals == False,tools 变 | ``change`` | ✅ |
| 上 header | headerEquals == True,开新 series(retry) | ``series`` | ✅ |

PR-0 只验证 fold 模块语义(reason / series 由 PR-2 publisher 状态决定);
本测试通过 :func:`foldRequestHeader` 端到端验证 fold 路径对各类变更的可
重建性(``foldRequestHeader`` 不依赖 reason,只看最后一条有效 header)。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lca_kernel.events.fold import (
    EpochHeader,
    StepEntry,
    StepTree,
    TurnEntry,
    canonicalHeader,
    fold_step_tree,
    foldRequestHeader,
    headerEquals,
)

CONFIG_BASE: dict[str, Any] = {"provider": "mock", "model": "m"}
CONFIG_OTHER: dict[str, Any] = {"provider": "mock", "model": "other"}


def tool(name: str, description: str = "d") -> dict[str, Any]:
    return {"name": name, "description": description, "parameters": {"type": "object"}}


def make_header_event(
    *,
    config: Mapping[str, Any] | None = None,
    system: str | None = None,
    tools: tuple[Mapping[str, Any], ...] = (),
    step_id: str | None = None,
) -> dict[str, Any]:
    """构造 fold 目标 event:``spine.llm.request.header`` 形态。"""
    payload: dict[str, Any] = {}
    if config is not None:
        payload["config"] = dict(config)
    if system is not None:
        payload["system"] = system
    if tools:
        payload["tools"] = list(tools)
    if step_id is not None:
        payload["step_id"] = step_id
    return {"category": "spine.llm.request.header", "payload": payload}


# ── 场景 1: 首次发 → fold 返回 initial header ──────────────────────────────


def test_fold_returns_initial_header_when_no_prior_state() -> None:
    """场景 1: 首次 ``spine.llm.request.header`` 落盘(``reason=initial``)。

    fold 端到端:无关事件不污染;返回 header 与唯一一条 canonical header 字节级等。
    """
    initial = make_header_event(config=CONFIG_BASE, system="first prompt")
    events: list[dict[str, Any]] = [
        {"category": "turn/start", "payload": {"turn": 1}},
        initial,
    ]

    folded = foldRequestHeader(events)
    assert folded == canonicalHeader(
        EpochHeader(config=CONFIG_BASE, system="first prompt", tools=())
    )
    assert folded is not None
    # canonical: 空 tools 归一为 ()
    assert folded.tools == ()


# ── 场景 2: 同 header 不发 → fold 仍能重建(取最近 header) ──────────────


def test_fold_reconstructs_when_consecutive_headers_are_equal() -> None:
    """场景 2: 连续相同 header(``reason=`` 不发)→ fold 仍取最近一条等值 header。

    fold 模块不依赖 publisher 的"不发"决策,只对落盘事件流负责;验证:
    两条 ``canonicalHeader(prev) == canonicalHeader(curr)`` 的事件在流里时,
    fold 结果与任一条 canonical header 字节级等。
    """
    same = EpochHeader(config=CONFIG_BASE, system="same prompt", tools=(tool("a"),))
    events: list[dict[str, Any]] = [
        make_header_event(config=CONFIG_BASE, system="same prompt", tools=(tool("a"),)),
        make_header_event(config=CONFIG_BASE, system="same prompt", tools=(tool("a"),)),
    ]

    folded = foldRequestHeader(events)
    assert folded is not None
    # 两条 header canonical 后字段一致
    assert headerEquals(folded, same) is True


# ── 场景 3: system 变化发 → fold 重建到变更后系统提示 ──────────────────


def test_fold_reconstructs_when_system_changes() -> None:
    """场景 3: system 字段变化(``reason=change``)→ fold 重建到变更后 system。"""
    events: list[dict[str, Any]] = [
        make_header_event(config=CONFIG_BASE, system="prompt v1"),
        make_header_event(config=CONFIG_BASE, system="prompt v2"),
    ]

    folded = foldRequestHeader(events)
    assert folded is not None
    assert folded.system == "prompt v2"
    # config 不变,字段级保留
    assert folded.config == CONFIG_BASE


# ── 场景 4: tools 变化发 → fold 重建到变更后工具集 ──────────────────────


def test_fold_reconstructs_when_tools_change() -> None:
    """场景 4: tools 集合变化(``reason=change``)→ fold 重建到变更后 tools。

    验证两种变化形态:

    - 增工具: ``[tool_a]`` → ``[tool_a, tool_b]``
    - 改工具: ``[tool_a]`` → ``[tool_a_v2]``
    """
    # 4a: 增工具
    events_add: list[dict[str, Any]] = [
        make_header_event(config=CONFIG_BASE, tools=(tool("a"),)),
        make_header_event(config=CONFIG_BASE, tools=(tool("a"), tool("b"))),
    ]
    folded_add = foldRequestHeader(events_add)
    assert folded_add is not None
    assert folded_add.tools == (tool("a"), tool("b"))

    # 4b: 改工具(同名但 description 变)
    events_change: list[dict[str, Any]] = [
        make_header_event(config=CONFIG_BASE, tools=(tool("a", "old"),)),
        make_header_event(config=CONFIG_BASE, tools=(tool("a", "new"),)),
    ]
    folded_change = foldRequestHeader(events_change)
    assert folded_change is not None
    assert folded_change.tools == (tool("a", "new"),)
    # 旧 canonical 与新 canonical 不等(headerEquals 字节级)
    assert (
        headerEquals(
            canonicalHeader(EpochHeader(config=CONFIG_BASE, tools=(tool("a", "old"),))),
            folded_change,
        )
        is False
    )


# ── 场景 5: 开新 series(retry)→ fold 仍能重建,语义不污染 ───────────────


def test_fold_reconstructs_when_new_series_opens_with_same_header() -> None:
    """场景 5: 开新 series(retry)header 字节级相同,但 publisher 选择落盘。

    fold 端: 取最近一条 header,与上一 series header canonical 后字段级等;
    fold 不感知 reason,只看落盘字节布局。本场景验证同一 header 跨 series
    fold 后结果稳定。
    """
    same_payload: dict[str, Any] = {
        "config": CONFIG_BASE,
        "system": "retry prompt",
        "tools": [tool("a")],
    }
    # step_id 不同(模拟开新 series),payload 字节级相同
    events: list[dict[str, Any]] = [
        {"category": "spine.llm.request.header", "payload": dict(same_payload)},
    ]
    series_1 = foldRequestHeader(events)
    assert series_1 is not None

    events.append({"category": "spine.llm.request.header", "payload": dict(same_payload)})
    series_2 = foldRequestHeader(events)
    assert series_2 is not None
    # 同一 header 跨 series canonical 后字段一致
    assert headerEquals(series_1, series_2) is True
    # system 仍为 retry prompt
    assert series_2.system == "retry prompt"


def test_fold_with_step_id_filter_isolates_one_step() -> None:
    """fold 在指定 ``step_id`` 时只 fold 该 step 的事件。

    验证 ``step_id`` 维度的 fold 隔离:不同 step 的 header 互不污染。
    """
    events: list[dict[str, Any]] = [
        {
            "category": "spine.llm.request.header",
            "payload": {
                "step_id": "step-001",
                "config": CONFIG_BASE,
                "system": "first",
            },
        },
        {
            "category": "spine.llm.request.header",
            "payload": {
                "step_id": "step-002",
                "config": CONFIG_OTHER,
                "system": "second",
            },
        },
    ]

    # 无 step_id 过滤:取最后一条
    assert foldRequestHeader(events) == EpochHeader(config=CONFIG_OTHER, system="second")

    # step_id=step-001:只 fold 该 step
    step_one = foldRequestHeader(events, step_id="step-001")
    assert step_one == EpochHeader(config=CONFIG_BASE, system="first")

    # step_id=step-002:只 fold 该 step
    step_two = foldRequestHeader(events, step_id="step-002")
    assert step_two == EpochHeader(config=CONFIG_OTHER, system="second")

    # step_id 命中 0 条事件:返回 None(无状态)
    assert foldRequestHeader(events, step_id="step-999") is None


def test_fold_with_from_baseline_continues_prior_state() -> None:
    """``from_`` 续接上次 fold 结果(增量 fold)。"""
    baseline = EpochHeader(config=CONFIG_BASE, system="baseline")
    events: list[dict[str, Any]] = [
        make_header_event(config=CONFIG_BASE, system="delta"),
    ]

    # 无 baseline + 空流 → None
    assert foldRequestHeader([]) is None

    # baseline + 空流 → baseline(增量 fold 不重置)
    assert foldRequestHeader([], from_=baseline) is baseline

    # baseline + 1 条新 header → 新 header 覆盖(走 canonical)
    result = foldRequestHeader(events, from_=baseline)
    assert result == canonicalHeader(EpochHeader(config=CONFIG_BASE, system="delta"))


# ── fold_step_tree 场景 ──────────────────────────────────────────────────────


def test_fold_step_tree_empty_stream_returns_empty_tree() -> None:
    """fold_step_tree: 空流返回空 StepTree。"""
    tree = fold_step_tree([])
    assert tree == StepTree()
    assert tree.turns == ()
    assert tree.active_turn is None
    assert tree.active_step is None


def test_fold_step_tree_single_turn_two_steps() -> None:
    """fold_step_tree: 单 turn + 两 step 完整开闭。"""
    events: list[dict[str, Any]] = [
        {"type": "turn/start", "data": {"turn": 0}},
        {"type": "step/start", "data": {"turn": 0, "step": 0}},
        {"type": "step/end", "data": {"turn": 0, "step": 0}},
        {"type": "step/start", "data": {"turn": 0, "step": 1}},
        {"type": "step/end", "data": {"turn": 0, "step": 1}},
        {"type": "turn/end", "data": {"turn": 0}},
    ]
    tree = fold_step_tree(events)
    assert len(tree.turns) == 1
    assert tree.turns[0] == TurnEntry(
        turn=0,
        started=True,
        ended=True,
        steps=(
            StepEntry(step=0, started=True, ended=True),
            StepEntry(step=1, started=True, ended=True),
        ),
    )
    assert tree.active_turn is None
    assert tree.active_step is None


def test_fold_step_tree_active_turn_and_step() -> None:
    """fold_step_tree: 未关闭的 turn/step 反映在 active_* 字段。"""
    events: list[dict[str, Any]] = [
        {"type": "turn/start", "data": {"turn": 1}},
        {"type": "step/start", "data": {"turn": 1, "step": 0}},
    ]
    tree = fold_step_tree(events)
    assert tree.active_turn == 1
    assert tree.active_step == (1, 0)
    assert tree.turns[0].started is True
    assert tree.turns[0].ended is False
    assert tree.turns[0].steps[0].started is True
    assert tree.turns[0].steps[0].ended is False


def test_fold_step_tree_skips_unrelated_events() -> None:
    """fold_step_tree: 非 turn/step 事件跳过。"""
    events: list[dict[str, Any]] = [
        {"type": "user/message", "data": {"content": "hi"}},
        {"type": "turn/start", "data": {"turn": 0}},
        {"type": "assistant/chunk", "data": {"text": "hello"}},
        {"type": "turn/end", "data": {"turn": 0}},
    ]
    tree = fold_step_tree(events)
    assert len(tree.turns) == 1
    assert tree.turns[0].turn == 0
    assert tree.turns[0].steps == ()


def test_fold_step_tree_from_continues_prior_state() -> None:
    """fold_step_tree: from_ 续接上次 fold 结果(增量 fold)。"""
    prior = fold_step_tree(
        [
            {"type": "turn/start", "data": {"turn": 0}},
            {"type": "step/start", "data": {"turn": 0, "step": 0}},
            {"type": "step/end", "data": {"turn": 0, "step": 0}},
        ]
    )
    assert prior.active_turn == 0

    tree = fold_step_tree(
        [
            {"type": "step/start", "data": {"turn": 0, "step": 1}},
            {"type": "step/end", "data": {"turn": 0, "step": 1}},
            {"type": "turn/end", "data": {"turn": 0}},
        ],
        from_=prior,
    )
    assert len(tree.turns) == 1
    assert len(tree.turns[0].steps) == 2
    assert tree.turns[0].ended is True
    assert tree.active_turn is None


def test_fold_step_tree_multiple_turns() -> None:
    """fold_step_tree: 多 turn 按序号排序。"""
    events: list[dict[str, Any]] = [
        {"type": "turn/start", "data": {"turn": 0}},
        {"type": "step/start", "data": {"turn": 0, "step": 0}},
        {"type": "step/end", "data": {"turn": 0, "step": 0}},
        {"type": "turn/end", "data": {"turn": 0}},
        {"type": "turn/start", "data": {"turn": 1}},
        {"type": "step/start", "data": {"turn": 1, "step": 0}},
    ]
    tree = fold_step_tree(events)
    assert len(tree.turns) == 2
    assert tree.turns[0].turn == 0
    assert tree.turns[0].ended is True
    assert tree.turns[1].turn == 1
    assert tree.turns[1].ended is False
    assert tree.active_turn == 1
    assert tree.active_step == (1, 0)
