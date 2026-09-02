"""ADR-0169 PR-11 (Incarnation):Incarnation 显式身份 + Registry + Cursor 派生。

覆盖:
    - Incarnation frozen 不可变 + 字段语义
    - child() 派生:继承 run_id + plan_ref,seq += 1
    - IncarnationRegistry 协议:add / lookup / derive_for_plan
    - Cursor snapshot.incarnation 与 Incarnation.incarnation_seq 一致
    - Cursor spine payload 携带 incarnation plan_ref + seq(L14 不变量)
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass, field

import pytest

from lca.contracts.observability.incarnation import (
    Incarnation,
    IncarnationRegistry,
)
from lca.contracts.observability.loop_cursor_payloads import (
    ThinkingRecord,
)
from lca.infrastructure.observability.loop_cursor import (
    InMemoryLoopCursor,
    StdLoopCursor,
)

# ── Incarnation dataclass ───────────────────────────────────────────


def test_incarnation_is_frozen() -> None:
    inc = Incarnation(run_id="r1", plan_ref="plan-A", incarnation_seq=1)
    with pytest.raises(FrozenInstanceError):
        inc.run_id = "r2"  # type: ignore[misc]


def test_incarnation_rejects_non_positive_seq() -> None:
    with pytest.raises(ValueError):
        Incarnation(run_id="r1", plan_ref="plan-A", incarnation_seq=0)
    with pytest.raises(ValueError):
        Incarnation(run_id="r1", plan_ref="plan-A", incarnation_seq=-1)


def test_child_increments_seq_and_inherits_identity() -> None:
    parent = Incarnation(run_id="r1", plan_ref="plan-A", incarnation_seq=3)
    child = parent.child()
    assert child.run_id == parent.run_id
    assert child.plan_ref == parent.plan_ref
    assert child.incarnation_seq == parent.incarnation_seq + 1
    # parent 不可变断言:派生不污染 parent
    assert parent.incarnation_seq == 3


def test_child_chain_is_monotonic() -> None:
    inc = Incarnation(run_id="r1", plan_ref="plan-A", incarnation_seq=1)
    seqs = [inc.incarnation_seq]
    for _ in range(5):
        inc = inc.child()
        seqs.append(inc.incarnation_seq)
    assert seqs == [1, 2, 3, 4, 5, 6]


# ── IncarnationRegistry Protocol ────────────────────────────────────


class _ListRegistry:
    """最小 IncarnationRegistry 实现 —— 内存里按 run_id 索引。"""

    def __init__(self) -> None:
        self._by_run: dict[str, Incarnation] = {}

    def register(self, run_id: str, plan_ref: str) -> Incarnation:
        inc = Incarnation(run_id=run_id, plan_ref=plan_ref, incarnation_seq=1)
        self._by_run[run_id] = inc
        return inc

    def lookup(self, run_id: str) -> Incarnation | None:
        return self._by_run.get(run_id)

    def derive_for_plan(self, run_id: str, plan_ref: str) -> Incarnation:
        prev = self._by_run.get(run_id)
        if prev is None:
            return self.register(run_id, plan_ref)
        # plan_ref 切换 → seq += 1
        next_seq = prev.incarnation_seq + 1
        new = Incarnation(run_id=run_id, plan_ref=plan_ref, incarnation_seq=next_seq)
        self._by_run[run_id] = new
        return new


def test_registry_register_and_lookup() -> None:
    reg: IncarnationRegistry = _ListRegistry()
    inc = reg.register("r1", "plan-A")
    assert inc.incarnation_seq == 1
    assert reg.lookup("r1") == inc
    assert reg.lookup("missing") is None


def test_registry_derive_for_plan_bumps_seq() -> None:
    reg: IncarnationRegistry = _ListRegistry()
    reg.register("r1", "plan-A")
    next_inc = reg.derive_for_plan("r1", "plan-B")
    assert next_inc.plan_ref == "plan-B"
    assert next_inc.incarnation_seq == 2
    # lookup 反映最新
    assert reg.lookup("r1") == next_inc


def test_registry_derive_for_unknown_run_registers() -> None:
    reg: IncarnationRegistry = _ListRegistry()
    inc = reg.derive_for_plan("fresh", "plan-X")
    assert inc.incarnation_seq == 1
    assert reg.lookup("fresh") == inc


# ── Cursor 派生: snapshot.incarnation 与 payload 携带 ────────────────


@dataclass
class _StubSpine:
    """捕获 append 调用,返回分配的 seq。"""

    records: list[dict] = field(default_factory=list)

    def append(
        self,
        *,
        execution_point: str,
        payload: dict,
        run_id: str,
        seq: int,
        incarnation: int,
        phase: str | None,
    ) -> int:
        self.records.append(
            {
                "execution_point": execution_point,
                "payload": payload,
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
        incarnation=Incarnation(run_id="r1", plan_ref="plan-A", incarnation_seq=2),
    )
    return cursor, spine


def test_cursor_snapshot_incarnation_matches_seq() -> None:
    c, _ = _make_std()
    assert c.snapshot.incarnation == 2
    # incarnation 属性暴露完整身份
    assert c.incarnation.plan_ref == "plan-A"
    assert c.incarnation.run_id == "r1"


def test_cursor_phase_fold_payload_carries_incarnation() -> None:
    c, spine = _make_std()
    c.advance("perceive")
    rec = spine.records[0]
    assert rec["execution_point"] == "phase.perceive.fold"
    assert rec["incarnation"] == 2


def test_cursor_record_thinking_payload_envelope_l14() -> None:
    c, spine = _make_std()
    c.advance("think")
    c.record_thinking(
        ThinkingRecord(
            content_digest="abc",
            content_path=None,
            token_count=10,
            thinking_kind="reasoning",
        )
    )
    last = spine.records[-1]
    assert last["execution_point"] == "step.thinking.record"
    # L14:envelope 必携带 plan_ref + incarnation_seq
    assert last["payload"]["plan_ref"] == "plan-A"
    assert last["payload"]["incarnation"] == 2


def test_cursor_fork_bumps_incarnation_seq_keeps_identity() -> None:
    c, _ = _make_std()
    child = c.fork("child_agent")
    assert isinstance(child, StdLoopCursor)
    # child 继承 run_id + plan_ref,seq += 1(ADR-0171 P4)
    assert child.snapshot.incarnation == 3
    assert child.incarnation.run_id == "r1"
    assert child.incarnation.plan_ref == "plan-A"


def test_in_memory_cursor_fork_bumps_incarnation_seq() -> None:
    c = InMemoryLoopCursor(
        run_id="r1",
        trace_id="t1",
        incarnation=Incarnation(run_id="r1", plan_ref="plan-A", incarnation_seq=5),
    )
    child = c.fork("child_agent")
    assert isinstance(child, InMemoryLoopCursor)
    assert child.snapshot.incarnation == 6
    assert child.incarnation.run_id == "r1"
    assert child.incarnation.plan_ref == "plan-A"


def test_cursor_chain_fork_monotonic_seq() -> None:
    c, _ = _make_std()
    seqs = [c.snapshot.incarnation]
    for _ in range(3):
        c = c.fork("delegation")
        seqs.append(c.snapshot.incarnation)
    assert seqs == [2, 3, 4, 5]
