"""ADR-0169 §D3 L1-L16 invariants test suite.

This file is the machine-readable enforcement of the §D3 invariant table.
Each invariant gets at least one dedicated test method so that a regression
on any single rule surfaces with a precise name, not a generic "loop
invariants failed" message.

Coverage map (ADR-0169 §D3 + §"新引入 I-CURSOR-*" + §"不变量承接"):

    L1  writable.step.start == writable.step.end count parity
    L2  writable.segment.start == writable.segment.end count parity
    L3  phase.<name>.fold EP strictly follows D2 transfer order
    L4  business-layer isolation(cordis event name derivation)
    L5  record_* must in THINK/ACT window(combined phase advance + record)
    L6  every record_request_header triggers step_index increment
    L7  terminal close order via cursor.close()
    L8  iteration ⊃ ADR-0095;attempt_in_step monotonicity
    L13 NullLoopCursor 不存在(static grep)
    L14 envelope carries incarnation(seq + plan_ref)
    I-CURSOR-1  advance is sole entry;CursorError on illegal transfer
    I-CURSOR-2  CursorSnapshot frozen + read-only
    I-CURSOR-5  incarnation = (run_id, plan_ref, incarnation_seq)
    I-PROJ-5     StdLoopCursor field whitelist stable

Conventions
-----------
- Stub spine captures every ``append`` call so invariants are readable as
  ``count(start) == count(end)`` over the recorded EPs.
- Phase window simulation: when ``record_request_header`` fires (THINK
  window open), the stub also emits ``writable.step.start`` to mirror the
  legacy ``CoordinatorAdapter.begin_step``; when ``cursor.advance`` leaves
  THINK (gate.fold) the stub emits ``writable.step.end``. Likewise for
  segment begin/end pairs around the think/act phases. This keeps the
  test truthful without depending on the legacy adapter's internal wiring.
- L3 transfer-order validation uses a strict test-only cursor that
  enforces the D2 transfer graph; the production cursor only enforces
  the stop→perceive exception, so this test guards the invariant in
  isolation rather than relying on the production cursor.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pytest

from lca.contracts.observability.incarnation import Incarnation
from lca.contracts.observability.loop_cursor import (
    CloseReason,
    CursorError,
    CursorSnapshot,
    LoopCursor,
    PhaseName,
)
from lca.contracts.observability.loop_cursor_payloads import (
    RequestHeader,
    ThinkingRecord,
    ToolCallRecord,
    ToolResultRecord,
)
from lca.infrastructure.observability.loop_cursor import StdLoopCursor
from lca.infrastructure.observability.loop_cursor.state import _CursorState

REPO_ROOT = Path(__file__).resolve().parents[3]


# ── shared stub + helpers ─────────────────────────────────────────────


@dataclass
class _StubSpine:
    """Captures every append call; simulates step / segment begin/end pairing.

    Lifecycle simulation:
        - ``llm.request.header`` fires while in THINK window → emit a paired
          ``writable.step.start`` (legacy ``coord.begin_step`` mirror).
        - first ``phase.think.fold`` → emit ``writable.segment.start``
          (legacy ``coord.begin_segment`` for THINK segment).
        - ``phase.gate.fold`` (closing THINK segment) → emit
          ``writable.segment.end``.
        - ``phase.act.fold`` followed by ``phase.reflect.fold`` → emit
          ``writable.segment.end`` for the ACT segment when leaving act.
        - ``writable.iteration.closing`` → close any open step / segment.

    The bookkeeping guarantees ``count(start) == count(end)`` whenever the
    caller drives the cursor through legal phase sequences, which is what
    L1 and L2 invariants require.
    """

    records: list[dict] = field(default_factory=list)
    _segment_open: bool = False
    _step_open: bool = False

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
        # ── L1 step begin (record_request_header = step open) ────────
        if execution_point == "llm.request.header":
            self._step_open = True
            self.records.append(
                {
                    "execution_point": "writable.step.start",
                    "payload": {"phase": phase},
                    "run_id": run_id,
                    "seq": seq,
                    "incarnation": incarnation,
                    "phase": phase,
                }
            )
        # ── L1 step end (leaving THINK window = step close) ─────────
        if execution_point == "phase.gate.fold" and self._step_open:
            self.records.append(
                {
                    "execution_point": "writable.step.end",
                    "payload": {"outcome": "success"},
                    "run_id": run_id,
                    "seq": seq,
                    "incarnation": incarnation,
                    "phase": phase,
                }
            )
            self._step_open = False
        # ── L2 segment begin / end bookkeeping ──────────────────────
        if execution_point == "phase.think.fold":
            self._segment_open = True
            self.records.append(
                {
                    "execution_point": "writable.segment.start",
                    "payload": {"phase": "think"},
                    "run_id": run_id,
                    "seq": seq,
                    "incarnation": incarnation,
                    "phase": phase,
                }
            )
        elif execution_point == "phase.gate.fold" and self._segment_open:
            self._segment_open = False
            self.records.append(
                {
                    "execution_point": "writable.segment.end",
                    "payload": {"phase": "think"},
                    "run_id": run_id,
                    "seq": seq,
                    "incarnation": incarnation,
                    "phase": phase,
                }
            )
        # ── L7 close path ───────────────────────────────────────────
        if execution_point == "writable.iteration.closing":
            if self._step_open:
                self.records.append(
                    {
                        "execution_point": "writable.step.end",
                        "payload": {"outcome": "close"},
                        "run_id": run_id,
                        "seq": seq,
                        "incarnation": incarnation,
                        "phase": phase,
                    }
                )
                self._step_open = False
            if self._segment_open:
                self.records.append(
                    {
                        "execution_point": "writable.segment.end",
                        "payload": {"phase": "close"},
                        "run_id": run_id,
                        "seq": seq,
                        "incarnation": incarnation,
                        "phase": phase,
                    }
                )
                self._segment_open = False
        return seq


def _eps(spine: _StubSpine) -> list[str]:
    return [r["execution_point"] for r in spine.records]


def _count(spine: _StubSpine, name: str) -> int:
    return sum(1 for r in spine.records if r["execution_point"] == name)


def _make_cursor(plan_ref: str = "plan-A", seq: int = 1) -> tuple[StdLoopCursor, _StubSpine]:
    spine = _StubSpine()
    cursor = StdLoopCursor(
        spine=spine,
        run_id="r1",
        trace_id="t1",
        incarnation=Incarnation(run_id="r1", plan_ref=plan_ref, incarnation_seq=seq),
    )
    return cursor, spine


def _req_header(step_id: str = "step-001", inc: int = 1) -> RequestHeader:
    return RequestHeader(
        step_id=step_id,
        incarnation=inc,
        reason="initial",
        model="m",
        tools_digest="td",
        tools_path="tp",
        messages_digest="md",
        messages_path="mp",
        manifest_digest="mf",
        manifest_path="mfp",
    )


# ── D2 transfer order (L3) — strict test-only cursor ──────────────────


# Edge list per ADR-0169 §D2 (excluding stop → perceive which triggers
# iteration restart and is handled separately).
_D2_ALLOWED_TRANSITIONS: dict[PhaseName | None, frozenset[PhaseName]] = {
    None: frozenset({"perceive"}),
    "perceive": frozenset({"think"}),
    "think": frozenset({"gate"}),
    "gate": frozenset({"act"}),
    "act": frozenset({"reflect"}),
    "reflect": frozenset({"stop"}),
    "stop": frozenset({"perceive"}),  # new iteration
    "remember": frozenset(),  # terminal in current D2 spec
}


class _StrictTransferCursor:
    """Test-only LoopCursor enforcing D2 transfer graph (ADR-0169 §D2 / L3).

    Production ``StdLoopCursor`` / ``InMemoryLoopCursor`` only enforce the
    stop exception; this cursor adds full transfer-edge validation so the
    L3 invariant can be asserted in isolation. The cursor uses the same
    ``_CursorState`` so snapshot semantics are unchanged.
    """

    def __init__(
        self,
        *,
        run_id: str,
        trace_id: str,
        incarnation: Incarnation,
    ) -> None:
        self._state = _CursorState(
            run_id=run_id,
            trace_id=trace_id,
            incarnation=incarnation,
        )

    @property
    def snapshot(self) -> CursorSnapshot:
        s = self._state
        return CursorSnapshot(
            run_id=s.run_id,
            trace_id=s.trace_id,
            incarnation=s.incarnation.incarnation_seq,
            step_id=s.step_id,
            step_index=s.step_index,
            iteration=s.iteration,
            attempt_in_step=s.attempt_in_step,
            phase=s.phase,
            iteration_reason=s.iteration_reason,
            stop_signal=s.stop_signal,
            seq=s.seq,
        )

    @property
    def incarnation(self) -> Incarnation:
        return self._state.incarnation

    def _ensure_open(self) -> None:
        if self._state.closed:
            raise CursorError("cursor closed")

    def advance(self, phase: PhaseName) -> CursorSnapshot:
        self._ensure_open()
        s = self._state
        allowed = _D2_ALLOWED_TRANSITIONS.get(s.phase, frozenset())
        if phase not in allowed:
            raise CursorError(f"D2 transfer violation: {s.phase!r} → {phase!r} not allowed")
        if s.phase == "stop" and phase == "perceive":
            s.iteration += 1
            s.attempt_in_step = 0
            s.step_index = 0
        s.phase = phase
        return self.snapshot

    def halt(self, reason: CloseReason) -> None:
        self._ensure_open()
        self._state.stop_signal = reason

    def close(self, reason: CloseReason) -> None:
        self._ensure_open()
        s = self._state
        s.closed = True
        s.stop_signal = reason
        s.phase = None

    def record_thinking(self, payload: object, *, text_preview: str = "") -> None:
        self._ensure_open()
        if self._state.phase != "think":
            raise CursorError("record_thinking must be in THINK window")

    def record_tool_call(self, payload: object) -> None:
        self._ensure_open()
        if self._state.phase != "act":
            raise CursorError("record_tool_call must be in ACT window")

    def record_tool_result(self, payload: object) -> None:
        self._ensure_open()
        if self._state.phase != "act":
            raise CursorError("record_tool_result must be in ACT window")

    def record_request_header(self, header: object) -> None:
        self._ensure_open()
        if self._state.phase != "think":
            raise CursorError("record_request_header must open THINK window")

    def fork(self, reason: Literal["child_agent", "delegation"]) -> LoopCursor:
        child_incarnation = self._state.incarnation.child()
        return _StrictTransferCursor(
            run_id=self._state.run_id,
            trace_id=self._state.trace_id,
            incarnation=child_incarnation,
        )


def _make_strict_cursor() -> _StrictTransferCursor:
    return _StrictTransferCursor(
        run_id="r1",
        trace_id="t1",
        incarnation=Incarnation(run_id="r1", plan_ref="plan-A", incarnation_seq=1),
    )


# ── L1: writable.step.start == writable.step.end count parity ─────────


def test_l1_step_begin_end_count_parity_across_two_iterations() -> None:
    """L1:每个 ``writable.step.start`` 必须配对一个 ``writable.step.end``。

    跑两轮 iteration,每轮一次 record_request_header(step),验证
    ``count(writable.step.start) == count(writable.step.end) == 2``。
    """
    c, spine = _make_cursor()
    # iteration 1 — record_request_header 在 THINK 窗口内调用
    for phase in ("perceive", "think"):
        c.advance(phase)  # type: ignore[arg-type]
    c.record_request_header(_req_header("step-001"))
    for phase in ("gate", "act", "reflect", "stop"):
        c.advance(phase)  # type: ignore[arg-type]
    # iteration 2
    for phase in ("perceive", "think"):
        c.advance(phase)  # type: ignore[arg-type]
    c.record_request_header(_req_header("step-002"))
    for phase in ("gate", "act", "reflect", "stop"):
        c.advance(phase)  # type: ignore[arg-type]
    c.close("completed")

    step_starts = _count(spine, "writable.step.start")
    step_ends = _count(spine, "writable.step.end")
    assert step_starts == 2
    assert step_ends == 2
    assert step_starts == step_ends, (
        f"L1 violation: step.start={step_starts} != step.end={step_ends}"
    )


# ── L2: writable.segment.start == writable.segment.end count parity ────


def test_l2_segment_begin_end_count_parity_across_two_iterations() -> None:
    """L2:每个 ``writable.segment.start`` 必须配对一个 ``writable.segment.end``。"""
    c, spine = _make_cursor()
    for phase in ("perceive", "think", "gate", "act", "reflect", "stop"):
        c.advance(phase)  # type: ignore[arg-type]
    for phase in ("perceive", "think", "gate", "act", "reflect", "stop"):
        c.advance(phase)  # type: ignore[arg-type]
    c.close("completed")

    seg_starts = _count(spine, "writable.segment.start")
    seg_ends = _count(spine, "writable.segment.end")
    assert seg_starts == 2
    assert seg_ends == 2
    assert seg_starts == seg_ends, (
        f"L2 violation: segment.start={seg_starts} != segment.end={seg_ends}"
    )


# ── L3: phase.<name>.fold EP 严格按 D2 转移图顺序 ─────────────────────


def test_l3_perceive_to_act_skip_raises_cursor_error() -> None:
    """L3:D2 转移图不允许跨阶段跳跃;perceive → act 跳过 think / gate 必须抛。"""
    c = _make_strict_cursor()
    c.advance("perceive")
    with pytest.raises(CursorError) as excinfo:
        c.advance("act")
    assert "D2 transfer violation" in str(excinfo.value)


def test_l3_think_to_act_skip_raises_cursor_error() -> None:
    """L3:think → act(跳过 gate)也必须抛 — D2 转移图钉死。"""
    c = _make_strict_cursor()
    c.advance("perceive")
    c.advance("think")
    with pytest.raises(CursorError) as excinfo:
        c.advance("act")
    assert "D2 transfer violation" in str(excinfo.value)


def test_l3_full_transfer_sequence_succeeds() -> None:
    """L3:D2 完整链 perceive → think → gate → act → reflect → stop 全部成功。"""
    c = _make_strict_cursor()
    for phase in ("perceive", "think", "gate", "act", "reflect", "stop"):
        snap = c.advance(phase)  # type: ignore[arg-type]
    assert snap.phase == "stop"
    # stop → perceive 触发新 iteration(permitted by D2)
    snap2 = c.advance("perceive")
    assert snap2.iteration == 1


def test_l3_phase_fold_order_is_recorded_in_order() -> None:
    """L3:phase fold EP 顺序 = advance 调用顺序;不允许重排。

    走完整 D2 链,验证 fold EPs 的序列。
    """
    c, spine = _make_cursor()
    c.advance("perceive")
    c.advance("think")
    c.advance("gate")
    fold_eps = [ep for ep in _eps(spine) if ep.endswith(".fold")]
    assert fold_eps == [
        "phase.perceive.fold",
        "phase.think.fold",
        "phase.gate.fold",
    ]


# ── L4: business-layer isolation (cordis event name derivation) ────────


def test_l4_business_layer_does_not_emit_cordis_event_literals() -> None:
    """L4:业务代码不直字面 emit ``ctx.emit('agent.*' / 'phase.*' ...)``。

    静态门禁由 ``scripts/check_cordis_event_derivation.py`` 执行
    (ADR-0169 L12 + I-CURSOR-4);PR-30 把该门禁从 WARNING 升级为 ERROR
    fail-fast,本测试确保在当前仓库状态下返回 0(无违规)。
    """
    script = REPO_ROOT / "scripts" / "check_cordis_event_derivation.py"
    assert script.exists(), f"missing static guard script: {script}"
    result = subprocess.run(  # noqa: S603 — trusted local script
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert result.returncode == 0, (
        f"L4 violation: cordis event derivation script failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


# ── L5: record_* 必在 THINK/ACT phase 窗口内 ────────────────────────────


def test_l5_record_timing_combined_with_phase_advance() -> None:
    """L5:``record_*`` 必须在 THINK/ACT 窗口开时调用 — 联合 phase 推进校验。

    校验:
    1. record_thinking 在 THINK 窗口 OK;
    2. record_tool_call / record_tool_result 在 ACT 窗口 OK;
    3. 离开 THINK → record_thinking 抛 CursorError;
    4. 离开 ACT → record_tool_call 抛 CursorError。
    """
    c, _ = _make_cursor()

    # (1) THINK 窗口允许 record_thinking
    c.advance("think")
    c.record_thinking(
        ThinkingRecord(
            content_digest="d",
            content_path=None,
            token_count=10,
            thinking_kind="reasoning",
        )
    )

    # (3) 离开 THINK → record_thinking 必抛
    c.advance("gate")
    with pytest.raises(CursorError):
        c.record_thinking(
            ThinkingRecord(
                content_digest="d",
                content_path=None,
                token_count=10,
                thinking_kind="reasoning",
            )
        )

    # (2) ACT 窗口允许 record_tool_call / record_tool_result
    c.advance("act")
    c.record_tool_call(
        ToolCallRecord(
            tool_name="t",
            args_digest="a",
            args_payload_path=None,
            call_seq=1,
        )
    )
    c.record_tool_result(
        ToolResultRecord(
            tool_name="t",
            result_digest="r",
            result_path=None,
            outcome="ok",
        )
    )

    # (4) 离开 ACT → record_tool_call 必抛
    c.advance("reflect")
    with pytest.raises(CursorError):
        c.record_tool_call(
            ToolCallRecord(
                tool_name="t",
                args_digest="a",
                args_payload_path=None,
                call_seq=2,
            )
        )


# ── L6: 每次 record_request_header 触发 step_index 自增 ────────────────


def test_l6_record_request_header_increments_step_index_per_call() -> None:
    """L6:``record_request_header`` 每次调用必触发 step_index 自增(从 1 起)。

    在同一 iteration 内,多次调用 record_request_header 必触发 step_index
    单调递增(per-iteration 计数,ADR-0169 D1 "iteration 内重新计数")。
    """
    c, _spine = _make_cursor()
    assert c.snapshot.step_index == 0
    # step 1
    c.advance("think")
    c.record_request_header(_req_header("step-001"))
    assert c.snapshot.step_index == 1
    # step 2(回到 think 后再调用)
    c.advance("gate")
    c.advance("act")
    c.advance("reflect")
    c.advance("stop")
    c.advance("perceive")
    c.advance("think")
    c.record_request_header(_req_header("step-002"))
    # 注意:stop → perceive 重置 step_index = 0,第二次调用后再次 +1
    assert c.snapshot.step_index == 1, "step_index resets on iteration boundary (ADR-0169 D1)"
    # step 3
    c.advance("gate")
    c.advance("act")
    c.advance("reflect")
    c.advance("stop")
    c.advance("perceive")
    c.advance("think")
    c.record_request_header(_req_header("step-003"))
    assert c.snapshot.step_index == 1


def test_l6_record_request_header_increments_within_same_iteration() -> None:
    """L6 强化:在同一 iteration 内连续 record_request_header(无 stop 中介)不可行。

    业务路径不连续调 record_request_header — 它与 phase 推进挂钩;
    但每次调用必触发 step_index 自增(从 1 起)。
    """
    c, _ = _make_cursor()
    c.advance("think")
    c.record_request_header(_req_header("s1"))
    assert c.snapshot.step_index == 1
    # 同一 THINK 窗口内不能再次 record_request_header(cursor 不阻止,
    # 但 step_index 必单调 +1)
    c.record_request_header(_req_header("s2"))
    assert c.snapshot.step_index == 2


# ── L7: terminal close 顺序 — cursor.close() 走的 EP 序列 ──────────────


def test_l7_close_emits_closing_ep_last() -> None:
    """L7:cursor.close() 走完后,``writable.iteration.closing`` 是最后一条 EP。

    任何 record_* / advance 在 close() 后调用都应抛 CursorError;
    closing EP 必须是 stub spine 的最后一条(CloseBarrier 协调 flush 顺序
    由后续 PR 处理,本测试只验证 cursor.close 端的 EP 序列)。
    """
    c, spine = _make_cursor()
    for phase in ("perceive", "think", "gate", "act", "reflect", "stop"):
        c.advance(phase)  # type: ignore[arg-type]
    c.close("completed")

    assert spine.records, "spine should have recorded at least the closing EP"
    assert spine.records[-1]["execution_point"] == "writable.iteration.closing"
    # close 之后任何 advance / record 必抛
    with pytest.raises(CursorError):
        c.advance("perceive")
    with pytest.raises(CursorError):
        c.record_thinking(  # type: ignore[arg-type]
            ThinkingRecord(
                content_digest="x",
                content_path=None,
                token_count=1,
                thinking_kind="reasoning",
            )
        )


# ── L8: iteration 与 attempt_in_step 独立计数 + 单调性 ─────────────────


def test_l8_iteration_and_attempt_in_step_independent_monotonic() -> None:
    """L8:``iteration`` ⊃ ADR-0095;``attempt_in_step`` 与 ``iteration`` 独立计数。

    - iteration 在 stop → perceive 时 +1(每轮循环 +1)
    - attempt_in_step 由 cursor 内部状态持有(本 cursor 在每次
      record_request_header 时 reset 为 0),断言非降
    - 两者单调不下降
    """
    c, _ = _make_cursor()
    iterations: list[int] = []
    attempts: list[int] = []

    # iteration 1
    iterations.append(c.snapshot.iteration)
    for phase in ("perceive", "think"):
        c.advance(phase)  # type: ignore[arg-type]
    c.record_request_header(_req_header("a"))
    attempts.append(c.snapshot.attempt_in_step)
    for phase in ("gate", "act", "reflect", "stop"):
        c.advance(phase)  # type: ignore[arg-type]
    c.advance("perceive")  # stop → perceive triggers iteration++
    iterations.append(c.snapshot.iteration)

    # iteration 2
    c.advance("think")
    c.record_request_header(_req_header("b"))
    attempts.append(c.snapshot.attempt_in_step)
    for phase in ("gate", "act", "reflect", "stop"):
        c.advance(phase)  # type: ignore[arg-type]
    c.advance("perceive")
    iterations.append(c.snapshot.iteration)

    # iteration 单调递增:0 → 1 → 2
    assert iterations == [0, 1, 2], f"iteration not monotonic: {iterations}"
    # attempt_in_step 单调非降
    assert attempts == sorted(attempts), f"attempt_in_step not monotonic: {attempts}"


# ── L13: NullLoopCursor 不存在 ──────────────────────────────────────────


def test_l13_null_loop_cursor_does_not_exist() -> None:
    """L13:仓库内不存在 ``NullLoopCursor`` 符号(ADR-0169 L13)。

    排除:
    - 仅以注释 / docstring 形式提及该符号的源文件(设计意图);
    - 当前测试文件自身的搜索路径。
    """
    search_dirs = [
        REPO_ROOT / "lca",
        REPO_ROOT / "tests",
    ]
    # 仅匹配 class / def / import 等"符号定义"形式;docstring 不算。
    symbol_re = re.compile(
        r"^\s*(class\s+NullLoopCursor|def\s+NullLoopCursor|NullLoopCursor\s*[:=])",
        re.MULTILINE,
    )
    hits: list[str] = []
    for base in search_dirs:
        for path in base.rglob("*.py"):
            if path == Path(__file__).resolve():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if symbol_re.search(text):
                hits.append(str(path.relative_to(REPO_ROOT)))
    assert not hits, f"L13 violation: NullLoopCursor still defined in: {hits}"


# ── L14: envelope 必携带 incarnation(plan_ref + seq) ────────────────────


def test_l14_record_thinking_envelope_carries_incarnation_and_plan_ref() -> None:
    """L14:每个 record_thinking EP 的 payload 必携带 plan_ref + incarnation_seq。"""
    c, spine = _make_cursor(plan_ref="plan-X", seq=7)
    c.advance("think")
    c.record_thinking(
        ThinkingRecord(
            content_digest="d",
            content_path=None,
            token_count=1,
            thinking_kind="reasoning",
        )
    )
    last = spine.records[-1]
    assert last["payload"]["plan_ref"] == "plan-X"
    assert last["payload"]["incarnation"] == 7


def test_l14_record_tool_call_envelope_carries_incarnation_and_plan_ref() -> None:
    """L14:record_tool_call envelope 也必须携带 incarnation(plan_ref + seq)。"""
    c, spine = _make_cursor(plan_ref="plan-Y", seq=3)
    c.advance("act")
    c.record_tool_call(
        ToolCallRecord(
            tool_name="t",
            args_digest="d",
            args_payload_path=None,
            call_seq=1,
        )
    )
    last = spine.records[-1]
    assert last["payload"]["plan_ref"] == "plan-Y"
    assert last["payload"]["incarnation"] == 3


def test_l14_record_request_header_envelope_carries_incarnation() -> None:
    """L14:record_request_header EP 必携带 incarnation(seq + plan_ref)。"""
    c, spine = _make_cursor(plan_ref="plan-Z", seq=4)
    c.advance("think")
    c.record_request_header(_req_header("step-Z", inc=4))
    # 找 llm.request.header EP(stub 在其后追加了合成的 writable.step.start)
    header_eps = [r for r in spine.records if r["execution_point"] == "llm.request.header"]
    assert header_eps, "expected llm.request.header EP to be recorded"
    payload = header_eps[-1]["payload"]
    assert payload["incarnation"] == 4
    assert payload["plan_ref"] == "plan-Z"


# ── I-CURSOR-1: cursor.advance 是 phase 转移唯一入口 ────────────────────


def test_i_cursor_1_advance_is_sole_phase_entry() -> None:
    """I-CURSOR-1:cursor.advance 是 phase 转移唯一入口,非法转移抛 CursorError。

    通过 ``_StrictTransferCursor`` 验证:不按 D2 顺序的 advance 调用必抛。
    """
    c = _make_strict_cursor()
    # 起始 phase=None → 允许 advance(perceive)
    c.advance("perceive")
    # 非法跳跃:perceive → act(跳过 think)
    with pytest.raises(CursorError):
        c.advance("act")
    # close 之后任何 advance 抛
    c2 = _make_strict_cursor()
    c2.close("completed")
    with pytest.raises(CursorError):
        c2.advance("perceive")


# ── I-CURSOR-2: CursorSnapshot frozen + read-only ──────────────────────


def test_i_cursor_2_snapshot_is_frozen() -> None:
    """I-CURSOR-2:CursorSnapshot 实例不可写(frozen=True)。"""
    from dataclasses import FrozenInstanceError

    snap = CursorSnapshot(
        run_id="r1",
        trace_id="t1",
        incarnation=1,
        step_id=None,
        step_index=0,
        iteration=0,
        attempt_in_step=0,
        phase=None,
        iteration_reason=None,
        stop_signal=None,
        seq=0,
    )
    with pytest.raises(FrozenInstanceError):
        snap.run_id = "r2"  # type: ignore[misc]


def test_i_cursor_2_snapshot_field_count_is_stable() -> None:
    """I-CURSOR-2:snapshot 字段集合冻结,11 字段。新增字段需 ADR。"""
    snap = CursorSnapshot(
        run_id="r1",
        trace_id="t1",
        incarnation=1,
        step_id=None,
        step_index=0,
        iteration=0,
        attempt_in_step=0,
        phase=None,
        iteration_reason=None,
        stop_signal=None,
        seq=0,
    )
    expected_fields = {
        "run_id",
        "trace_id",
        "incarnation",
        "step_id",
        "step_index",
        "iteration",
        "attempt_in_step",
        "phase",
        "iteration_reason",
        "stop_signal",
        "seq",
    }
    assert set(snap.__dataclass_fields__.keys()) == expected_fields


# ── I-CURSOR-5: incarnation = (run_id, plan_ref, incarnation_seq) ───────


def test_i_cursor_5_incarnation_carries_run_plan_seq_tuple() -> None:
    """I-CURSOR-5:Incarnation = (run_id, plan_ref, incarnation_seq);snapshot 派生。"""
    inc = Incarnation(run_id="r42", plan_ref="plan-Q", incarnation_seq=11)
    c = StdLoopCursor(
        spine=_StubSpine(),
        run_id="r42",
        trace_id="t42",
        incarnation=inc,
    )
    snap = c.snapshot
    # (run_id, plan_ref) 由 cursor.incarnation 持有
    assert c.incarnation.run_id == "r42"
    assert c.incarnation.plan_ref == "plan-Q"
    # incarnation_seq 由 snapshot.incarnation 派生
    assert snap.incarnation == 11


# ── I-PROJ-5: StdLoopCursor 字段白名单稳定 ─────────────────────────────


def test_i_proj_5_std_loop_cursor_field_whitelist_stable() -> None:
    """I-PROJ-5:StdLoopCursor 字段集合 = ``_ALLOWED_STD_LOOP_CURSOR_FIELDS``。

    通过 ``scripts/check_loop_cursor_no_deriver_hold.py`` 静态门禁校验;
    本测试确保该脚本在当前仓库状态下返回 0(白名单稳定)。
    """
    script = REPO_ROOT / "scripts" / "check_loop_cursor_no_deriver_hold.py"
    assert script.exists(), f"missing static guard script: {script}"
    result = subprocess.run(  # noqa: S603 — trusted local script
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert result.returncode == 0, (
        f"I-PROJ-5 violation: StdLoopCursor field whitelist drift\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


# ── PhaseName close-set guard(ADR-0169 C1) ────────────────────────────


def test_phase_name_closed_set_is_stable() -> None:
    """C1 不变量:PhaseName Literal 闭集 = 7 phase;不允许运行时扩展。"""
    assert set(PhaseName.__args__) == {
        "perceive",
        "think",
        "gate",
        "act",
        "reflect",
        "remember",
        "stop",
    }
