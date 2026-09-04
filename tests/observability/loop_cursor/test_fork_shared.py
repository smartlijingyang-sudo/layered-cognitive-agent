"""ADR-0171 PR-4:fork 共享 Host 协议 — child cursor 共享 spine + bump incarnation_seq。

覆盖(per ADR-0171 D1 / D6 + I-FORK-1):
    - child 与 parent 持有同一 spine 实例(I-FORK-1:无独立 host / persistence)
    - Incarnation 继承 parent.run_id + parent.plan_ref,incarnation_seq += 1
    - child 的 iteration / step_index / attempt_in_step / seq 独立计数
    - fork EP ``loop.fork`` payload 携带 reason + child incarnation(ADR-0169 L14)
    - 链式 fork:incarnation_seq 单调递增
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

import pytest

from lca.contracts.observability.incarnation import Incarnation
from lca.contracts.observability.loop_cursor import (
    CursorError,
    LoopCursor,
)
from lca.infrastructure.observability.loop_cursor import (
    InMemoryLoopCursor,
    StdLoopCursor,
)

# ── Stub WritePort(per contracts/observability/loop_cursor_payloads WritePort) ────


@dataclass
class _StubSpine:
    """记录所有 append 调用;返回分配的 seq;暴露实例身份供断言使用。"""

    records: list[dict[str, Any]] = field(default_factory=list)

    def append(
        self,
        *,
        execution_point: str,
        payload: dict[str, Any],
        run_id: str,
        seq: int,
        incarnation: int,
        phase: str | None,
    ) -> int:
        self.records.append(
            {
                "execution_point": execution_point,
                "payload": dict(payload),
                "run_id": run_id,
                "seq": seq,
                "incarnation": incarnation,
                "phase": phase,
            }
        )
        return seq


def _make_std() -> tuple[StdLoopCursor, _StubSpine]:
    spine = _StubSpine()
    cursor = StdLoopCursor(
        spine=spine,
        run_id="r1",
        trace_id="t1",
        incarnation=Incarnation(run_id="r1", plan_ref="plan-A", incarnation_seq=3),
    )
    return cursor, spine


def _make_in_memory(seq: int = 3) -> InMemoryLoopCursor:
    return InMemoryLoopCursor(
        run_id="r1",
        trace_id="t1",
        incarnation=Incarnation(run_id="r1", plan_ref="plan-A", incarnation_seq=seq),
    )


# ── I-FORK-1:child 共享 parent spine handle ────────────────────────


def test_fork_child_shares_spine_handle() -> None:
    """child cursor 必须持 parent 的同一 spine 实例 —— I-FORK-1。"""
    parent, spine = _make_std()
    assert hasattr(parent, "advance")
    child = parent.fork("child_agent")
    assert isinstance(child, StdLoopCursor)

    # spine 是 Python 对象:``is`` 验证同一实例
    assert child._spine is spine
    assert child._spine is parent._spine

    # 写入 child 的 event 必落 parent 的同一 spine
    child.advance("perceive")
    assert len(spine.records) >= 1
    last = spine.records[-1]
    assert last["execution_point"] == "phase.perceive.fold"


# ── I-CURSOR-6 / P4:Incarnation 继承 + incarnation_seq += 1 ─────────


def test_fork_child_increments_incarnation_seq() -> None:
    parent, _ = _make_std()
    assert parent.snapshot.incarnation == 3
    child = parent.fork("delegation")
    # I-CURSOR-6:incarnation_seq = parent + 1
    assert child.snapshot.incarnation == 4
    # 身份继承:run_id + plan_ref
    assert child.incarnation.run_id == "r1"
    assert child.incarnation.plan_ref == "plan-A"
    # parent 不可变断言
    assert parent.snapshot.incarnation == 3


def test_in_memory_fork_child_increments_incarnation_seq() -> None:
    parent = _make_in_memory(seq=5)
    child = parent.fork("child_agent")
    assert child.snapshot.incarnation == 6
    assert child.incarnation.run_id == "r1"
    assert child.incarnation.plan_ref == "plan-A"


# ── I-FORK-1:child 计数独立(seq / iteration / step_index / attempt) ──


def test_fork_child_independent_iteration() -> None:
    """child 的 iteration 独立计数 —— 不继承 parent。"""
    parent, _ = _make_std()
    parent.advance("perceive")
    parent.advance("think")
    parent.advance("stop")
    # parent 重启 iteration (stop → perceive)
    parent.advance("perceive")
    parent.advance("stop")
    parent.advance("perceive")  # 第二轮:iteration == 2
    assert parent.snapshot.iteration == 2

    child = parent.fork("child_agent")
    # child 重置 iteration(独立计数,I-FORK-1)
    assert child.snapshot.iteration == 0
    assert child.snapshot.phase is None


def test_fork_child_independent_step_index() -> None:
    """child 的 step_index 独立计数 —— 不继承 parent。"""
    parent, _ = _make_std()
    parent.advance("think")
    parent.record_request_header(_stub_header(step_id="step-001", incarnation=3))
    assert parent.snapshot.step_index == 1

    child = parent.fork("delegation")
    # child 重置 step_index,phase 回到 OUTSIDE_LOOP
    assert child.snapshot.step_index == 0
    assert child.snapshot.step_id is None
    assert child.snapshot.phase is None


# ── L14 / D6:loop.fork EP payload 携带 child incarnation ───────────


def test_fork_records_carry_new_incarnation_in_payload() -> None:
    """fork 必须落 ``loop.fork`` EP,payload 携带 child incarnation_seq(ADR-0169 L14)。"""
    parent, spine = _make_std()
    # 父先推进 → seq 自增,然后 fork
    parent.advance("perceive")
    parent.advance("think")
    pre_count = len(spine.records)
    parent.fork("child_agent")

    last = spine.records[-1]
    assert last["execution_point"] == "loop.fork"
    assert last["payload"]["reason"] == "child_agent"
    # L14:payload 携带 child incarnation
    assert last["payload"]["parent_incarnation"] == 3
    assert last["payload"]["child_incarnation"] == 4
    assert last["payload"]["plan_ref"] == "plan-A"
    # seq 自增(父 cursor 的 seq 计数器)
    assert last["seq"] > 0
    assert len(spine.records) == pre_count + 1


def test_fork_records_delegation_reason() -> None:
    """reason 字段穿透到 payload。"""
    parent, spine = _make_std()
    parent.fork("delegation")
    assert spine.records[-1]["payload"]["reason"] == "delegation"


# ── I-FORK-1:链式 fork:incarnation_seq 单调 ────────────────────────


def test_chained_fork_increments_monotonically() -> None:
    """连续 fork → incarnation_seq 严格单调递增(ADR-0065 L3)。"""
    parent, _ = _make_std()
    seqs = [parent.snapshot.incarnation]
    cursor: LoopCursor = parent
    for _ in range(5):
        cursor = cursor.fork("child_agent")
        seqs.append(cursor.snapshot.incarnation)
    # 3, 4, 5, 6, 7, 8
    assert seqs == [3, 4, 5, 6, 7, 8]
    # 严格单调
    assert all(b > a for a, b in pairwise(seqs))


def test_chained_fork_in_memory_increments_monotonically() -> None:
    parent = _make_in_memory(seq=1)
    seqs = [parent.snapshot.incarnation]
    cursor: LoopCursor = parent
    for _ in range(4):
        cursor = cursor.fork("delegation")
        seqs.append(cursor.snapshot.incarnation)
    assert seqs == [1, 2, 3, 4, 5]


# ── I-FORK-1:child 写入走共享 spine(seq 在父 cursor 维度递增) ───────


def test_fork_child_writes_to_shared_spine() -> None:
    """child 写入的 EP 必须落在 parent 的 spine(单写 L10)。"""
    parent, spine = _make_std()
    # parent 先写 phase EP,确保 fork 后能区分
    parent.advance("perceive")
    parent.advance("think")
    child = parent.fork("child_agent")
    # child 推 phase
    child.advance("perceive")
    child.advance("think")
    # spine 是共享的;child 的 phase.X.fold EP 必落同一 spine
    phase_eps = [
        r
        for r in spine.records
        if r["execution_point"].startswith("phase.") and r["execution_point"].endswith(".fold")
    ]
    # parent(perceive + think) + child(perceive + think) = 4
    assert len(phase_eps) == 4
    # child 的 phase EP 携带 child incarnation(4)
    child_phase_eps = [r for r in phase_eps if r["incarnation"] == 4]
    assert len(child_phase_eps) == 2


# ── 关 cursor 之后 fork 必 raise ───────────────────────────────────


def test_fork_after_close_raises() -> None:
    parent, _ = _make_std()
    parent.close("completed")
    with pytest.raises(CursorError):
        parent.fork("child_agent")


# ── helper ──────────────────────────────────────────────────────────


def _stub_header(*, step_id: str, incarnation: int) -> Any:
    """构造最小 RequestHeader —— 仅用于测试 step_index 自增。"""
    from lca.contracts.observability.loop_cursor_payloads import RequestHeader

    return RequestHeader(
        step_id=step_id,
        incarnation=incarnation,
        reason="initial",
        model="m",
        tools_digest="d2",
        tools_path="p2",
        messages_digest="d3",
        messages_path="p3",
        manifest_digest="d4",
        manifest_path="p4",
    )
