"""ADR-0169 PR-15 PersistenceCoordinator integration:hard checkpoint for L1.

This file is the dedicated hard checkpoint for ``writable.step.start`` /
``writable.step.end`` parity (ADR-0169 L1). It walks the cursor through
multiple phase windows that open / close segments (think, act) and asserts
the spine always carries a balanced count of begin / end EPs — regardless of
which iteration boundary the cursor crosses.

Why "hard checkpoint"
---------------------
L1 is the load-bearing invariant of the persistence boundary: if
``writable.step.start`` and ``writable.step.end`` diverge, replay cannot
reconstruct step boundaries and ``PersistenceCoordinator.flush()`` may
commit a half-open step. The §D3 invariant table calls for grep-based
verification on ``events.jsonl``; this test is the in-process counterpart
that runs without I/O so failures surface in the unit-test loop.

The stub spine mirrors the legacy ``CoordinatorAdapter`` semantics:
``record_request_header`` opens a step (``writable.step.start``),
``phase.gate.fold`` (leaving THINK) closes the step
(``writable.step.end``); segment boundaries track the think window in the
same way. This is faithful to the bridge behaviour without depending on
its internal wiring.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lca.contracts.observability.incarnation import Incarnation
from lca.contracts.observability.loop_cursor_payloads import RequestHeader
from lca.infrastructure.observability.loop_cursor import StdLoopCursor

# ── stub spine + helpers ──────────────────────────────────────────────


@dataclass
class _StubSpine:
    """Captures every append call; emits paired begin/end EPs for segments.

    Lifecycle mirroring the legacy ``CoordinatorAdapter`` (ADR-0169 PR-15
    PersistenceCoordinator integration):
        - ``llm.request.header`` fires while in THINK → pair emits
          ``writable.step.start`` (step open).
        - ``phase.gate.fold`` (leaving THINK) → emits ``writable.step.end``
          (step close) and closes any open segment.
        - ``phase.think.fold`` → opens a segment.
        - ``phase.act.fold`` followed by ``phase.reflect.fold`` →
          closes the ACT segment.

    For ``writable.iteration.closing``: legacy ordering is
    ``step.end → segment.end → closing`` (close path first closes any
    open step / segment, then emits the closing signal). The stub
    prepends the close-out EPs before the cursor's own closing EP.

    The bookkeeping guarantees ``count(start) == count(end)`` whenever the
    caller drives the cursor through legal phase sequences — which is the
    L1 / L2 invariant under test.
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
        # close path:prepend close-out EPs before cursor's closing EP
        # so the cursor's writable.iteration.closing stays as the last
        # record in the trace (faithful to legacy coord ordering).
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
        # step begin
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
        # step end (leaving THINK window)
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
        # segment begin
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
        # segment end (leaving THINK)
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
        return seq


def _make_cursor(plan_ref: str = "plan-A", seq: int = 1) -> tuple[StdLoopCursor, _StubSpine]:
    spine = _StubSpine()
    cursor = StdLoopCursor(
        spine=spine,
        run_id="r1",
        trace_id="t1",
        incarnation=Incarnation(run_id="r1", plan_ref=plan_ref, incarnation_seq=seq),
    )
    return cursor, spine


def _req_header(step_id: str = "step-001") -> RequestHeader:
    return RequestHeader(
        step_id=step_id,
        incarnation=1,
        reason="initial",
        model="m",
        system_digest="sd",
        system_path="sp",
        tools_digest="td",
        tools_path="tp",
        messages_digest="md",
        messages_path="mp",
        manifest_digest="mf",
        manifest_path="mfp",
    )


def _count(spine: _StubSpine, name: str) -> int:
    return sum(1 for r in spine.records if r["execution_point"] == name)


# ── hard checkpoint tests ─────────────────────────────────────────────


def test_segment_start_emitted_when_phase_window_opens() -> None:
    """verify:writable.segment.start EP 在 phase window 开启时(think.fold)被 emit。

    走 1 个 iteration:perceive → think → gate → act → reflect → stop。
    - 走到 ``phase.think.fold`` 时 spine 必出现一条 ``writable.segment.start``。
    - segment.start 必须在 records 中出现在 ``phase.think.fold`` 之后。
    """
    c, spine = _make_cursor()
    for phase in ("perceive", "think"):
        c.advance(phase)  # type: ignore[arg-type]
    # 此时 segment.start 必已 emit
    assert _count(spine, "writable.segment.start") == 1, (
        "writable.segment.start must be emitted on phase.think.fold"
    )
    # 验证 records 列表中:phase.think.fold 先于 writable.segment.start
    think_idx = next(
        i for i, r in enumerate(spine.records) if r["execution_point"] == "phase.think.fold"
    )
    seg_idx = next(
        i for i, r in enumerate(spine.records) if r["execution_point"] == "writable.segment.start"
    )
    assert seg_idx > think_idx, "writable.segment.start must come after phase.think.fold in records"
    # phase.think.fold 之前(perceive.fold)不应触发 segment.start
    perceive_idx = next(
        i for i, r in enumerate(spine.records) if r["execution_point"] == "phase.perceive.fold"
    )
    assert perceive_idx < seg_idx, "writable.segment.start must come after phase.perceive.fold"


def test_segment_end_emitted_when_phase_window_closes() -> None:
    """verify:writable.segment.end EP 在 phase window 关闭时(gate.fold)被 emit。

    走 1 个 iteration:perceive → think → gate → act → reflect → stop。
    - 走到 ``phase.gate.fold`` 时 spine 必出现一条 ``writable.segment.end``。
    - segment.end 必须在 records 中出现在 ``phase.gate.fold`` 之后。
    """
    c, spine = _make_cursor()
    for phase in ("perceive", "think", "gate"):
        c.advance(phase)  # type: ignore[arg-type]
    # 此时 segment.end 必已 emit
    assert _count(spine, "writable.segment.end") == 1, (
        "writable.segment.end must be emitted on phase.gate.fold (leaving THINK)"
    )
    gate_idx = next(
        i for i, r in enumerate(spine.records) if r["execution_point"] == "phase.gate.fold"
    )
    seg_end_idx = next(
        i for i, r in enumerate(spine.records) if r["execution_point"] == "writable.segment.end"
    )
    assert seg_end_idx > gate_idx, "writable.segment.end must come after phase.gate.fold in records"


def test_count_segment_start_equals_count_segment_end_three_phases() -> None:
    """verify:走 3 个 phase 链后 count(start) == count(end)。

    每轮 iteration 走完整 phase 链(包括 think/act),验证 segment
    begin/end EP 数严格相等。
    """
    c, spine = _make_cursor()
    # 3 个完整 iteration,每轮 think → gate → act → reflect → stop
    for _ in range(3):
        for phase in ("perceive", "think", "gate", "act", "reflect", "stop"):
            c.advance(phase)  # type: ignore[arg-type]
    starts = _count(spine, "writable.segment.start")
    ends = _count(spine, "writable.segment.end")
    assert starts == 3, f"expected 3 segment.start, got {starts}"
    assert ends == 3, f"expected 3 segment.end, got {ends}"
    assert starts == ends, f"L2 violation: count(start)={starts} != count(end)={ends}"


def test_segment_begin_end_pairing_with_record_request_header() -> None:
    """verify:step.begin/end 也必须在 record_request_header 触发时配对。

    同一 iteration 内,每次 record_request_header → writable.step.start;
    离开 THINK 窗口 → writable.step.end。三次完整 iteration 后
    count(start) == count(end) == 3。
    """
    c, spine = _make_cursor()
    for i in range(3):
        c.advance("perceive")
        c.advance("think")
        c.record_request_header(_req_header(f"step-{i}"))
        for phase in ("gate", "act", "reflect", "stop"):
            c.advance(phase)  # type: ignore[arg-type]
    c.close("completed")

    starts = _count(spine, "writable.step.start")
    ends = _count(spine, "writable.step.end")
    assert starts == 3, f"expected 3 step.start, got {starts}"
    assert ends == 3, f"expected 3 step.end, got {ends}"
    assert starts == ends, f"L1 violation: step.start={starts} != step.end={ends}"


def test_segment_close_on_cursor_close_balances_open_segments() -> None:
    """verify:cursor.close() 在中途(segment 未关)时,close EP 强制平衡 segment。

    走 2 轮 iteration,最后一轮只到 think(不走到 gate),然后 close;
    close 路径必须 emit 缺失的 segment.end + step.end,使最终
    count(start) == count(end)。
    """
    c, spine = _make_cursor()
    # iteration 1 走完整
    for phase in ("perceive", "think", "gate", "act", "reflect", "stop"):
        c.advance(phase)  # type: ignore[arg-type]
    # iteration 2 只走到 think(segment 开但未关)
    for phase in ("perceive", "think"):
        c.advance(phase)  # type: ignore[arg-type]
    c.close("error")

    starts = _count(spine, "writable.segment.start")
    ends = _count(spine, "writable.segment.end")
    assert starts == 2, f"expected 2 segment.start, got {starts}"
    assert ends == 2, f"expected 2 segment.end (incl close-paired), got {ends}"
    assert starts == ends, f"L2 violation after close: start={starts} != end={ends}"

    # 验证 closing EP 是最后一条
    assert spine.records[-1]["execution_point"] == "writable.iteration.closing"
