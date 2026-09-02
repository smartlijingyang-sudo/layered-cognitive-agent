"""ADR-0169 PR-25:CoordinatorAdapter 测试。

桥接器把 ``StepCoordinator`` 旧 API 翻译到 ``LoopCursor`` 新 API;本测试
验证:
- ``adapter.begin_step(phase)`` → ``cursor.advance(phase)`` 派生 phase fold EP
- ``adapter.record_thinking / record_tool_call / record_tool_result`` →
  cursor.record_* 派生对应 EP(payload 字段映射正确)
- ``adapter.emit_phase(phase=...)`` → cursor.advance(phase) 派生 phase fold
- ``adapter.close(reason)`` → cursor.close(reason) 触发 writable.iteration.closing
- 旧 ``coord.*`` 仍可用(双写 compat)

业务代码 PR-25 阶段不切换;本测试只验桥接行为,直接用 cursor + coord。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lca.contracts.models.observability.journal_step import (
    ReflectTrace,
    SpanRecord,
    ThinkingTrace,
    ToolCallRecord as LegacyToolCallRecord,
    ToolResult as LegacyToolResult,
)
from lca.contracts.observability.incarnation import Incarnation
from lca.contracts.observability.loop_cursor import CursorSnapshot
from lca.infrastructure.observability.loop_cursor import StdLoopCursor
from lca.infrastructure.observability.loop_cursor._spine_port import WritePort
from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
    CoordinatorAdapter,
)
from lca.infrastructure.observability.writable_matrix.coordinator import StepCoordinator
from lca.infrastructure.observability.writable_matrix.registry import (
    WritableFaceRegistry,
)


# ── Stubs ───────────────────────────────────────────────────


@dataclass
class _StubSpine(WritePort):
    """捕获所有 append 调用的 stub spine。"""

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


@dataclass
class _StubStorage:
    """StepCoordinator 需要的最小 storage face。"""

    lines: list[str] = field(default_factory=list)

    def write(self, payload: bytes) -> None:
        self.lines.append(payload.decode("utf-8", errors="replace"))

    def close(self) -> None:
        return None


@dataclass
class _StubSerializer:
    def serialize(self, record: object) -> bytes:
        return b"{}"


@dataclass
class _StubEmitter:
    def emit(self, record: object) -> None:
        return None


@dataclass
class _StubCoalescer:
    def feed(self, key: str, payload: dict) -> None:
        return None

    def flush(self) -> tuple:
        return ()


@dataclass
class _StubDriver:
    """StepDriver face —— 返回固定 step_id / segment_id。"""

    _counter: int = 0

    def begin_step(self, phase: str, **ctx: object) -> str:
        self._counter += 1
        return f"step-{self._counter:03d}"

    def end_step(self, step_id: str, outcome: str) -> None:
        return None

    def begin_segment(self, step_id: str, kind: str) -> str:
        self._counter += 1
        return f"seg-{self._counter:03d}"

    def end_segment(self, seg_id: str, outcome: str) -> None:
        return None


def _build_registry() -> WritableFaceRegistry:
    reg = WritableFaceRegistry()
    reg.register("emitter", _StubEmitter())
    reg.register("driver", _StubDriver())
    reg.register("coalescer", _StubCoalescer())
    reg.register("serializer", _StubSerializer())
    reg.register("storage", _StubStorage())
    return reg


def _build_adapter() -> tuple[CoordinatorAdapter, _StubSpine, StepCoordinator]:
    spine = _StubSpine()
    cursor = StdLoopCursor(
        spine=spine,
        run_id="r1",
        trace_id="t1",
        incarnation=Incarnation(run_id="r1", plan_ref="plan-A", incarnation_seq=1),
    )
    coord = StepCoordinator(registry=_build_registry(), run_id="r1", trace_id="t1")
    return CoordinatorAdapter(cursor=cursor, coord=coord), spine, coord


# ── Tests ───────────────────────────────────────────────────


def test_adapter_begin_step_triggers_cursor_advance() -> None:
    """``adapter.begin_step('think')`` → cursor.advance('think') 派生 phase.think.fold EP。"""
    adapter, spine, _ = _build_adapter()
    step_id = adapter.begin_step("think")

    # 1) coord.begin_step 触发了 writable.step.start EP(Coord 五面矩阵)
    # 2) cursor.advance('think') 触发了 phase.think.fold EP(spine)
    eps = [r["execution_point"] for r in spine.records]
    assert "phase.think.fold" in eps
    # cursor.snapshot.phase == 'think'
    snap: CursorSnapshot = adapter.cursor.snapshot
    assert snap.phase == "think"
    assert step_id.startswith("step-")


def test_adapter_record_thinking_emits_cursor_thinking_ep() -> None:
    """``adapter.record_thinking(trace)`` → cursor.record_thinking 派生 EP + 旧 coord.record_thinking。"""
    adapter, spine, _ = _build_adapter()
    # 先开 think window
    adapter.begin_step("think")

    trace = ThinkingTrace(
        model="m",
        latency_ms=42,
        reasoning="reasoning text",
        decision="use_tool",
        prompt_tokens=10,
        completion_tokens=20,
    )
    adapter.record_thinking(trace)

    eps = [r["execution_point"] for r in spine.records]
    assert "step.thinking.record" in eps

    # payload 字段映射:token_count = prompt + completion = 30
    thinking_ep = next(r for r in spine.records if r["execution_point"] == "step.thinking.record")
    assert thinking_ep["payload"]["content_digest"] == "reasoning text"
    assert thinking_ep["payload"]["token_count"] == 30
    assert thinking_ep["payload"]["thinking_kind"] == "reasoning"
    assert thinking_ep["payload"]["incarnation"] == 1


def test_adapter_record_tool_call_emits_cursor_tool_call_ep() -> None:
    """``adapter.record_tool_call(call)`` → cursor.record_tool_call 派生 EP。"""
    adapter, spine, _ = _build_adapter()
    adapter.begin_step("think")
    adapter.cursor.advance("act")  # record_tool_call 必须在 ACT window

    call = LegacyToolCallRecord(
        invocation_id="inv-001",
        name="echo",
        arguments={"x": 1},
        arguments_summary="echo(x=1)",
    )
    adapter.record_tool_call(call)

    eps = [r["execution_point"] for r in spine.records]
    assert "step.tool_call.record" in eps
    call_ep = next(r for r in spine.records if r["execution_point"] == "step.tool_call.record")
    assert call_ep["payload"]["tool_name"] == "echo"
    assert call_ep["payload"]["args_digest"] == "echo(x=1)"


def test_adapter_record_tool_result_emits_cursor_tool_result_ep() -> None:
    """``adapter.record_tool_result(result)`` → cursor.record_tool_result 派生 EP。"""
    adapter, spine, _ = _build_adapter()
    adapter.begin_step("think")
    adapter.cursor.advance("act")

    result = LegacyToolResult(
        ok=True,
        latency_ms=15,
        delta_summary="echoed",
    )
    adapter.record_tool_result(result)

    eps = [r["execution_point"] for r in spine.records]
    assert "step.tool_result.record" in eps
    result_ep = next(r for r in spine.records if r["execution_point"] == "step.tool_result.record")
    assert result_ep["payload"]["outcome"] == "ok"
    assert result_ep["payload"]["result_digest"] == "echoed"


def test_adapter_emit_phase_advances_cursor_phase_window() -> None:
    """``adapter.emit_phase(phase='perceive', ...)`` → cursor.advance('perceive') 派生 phase.perceive.fold EP。"""
    adapter, spine, _ = _build_adapter()

    adapter.emit_phase(
        phase="perceive",
        objective="collect context",
        summary="perceived 3 items",
        outcome="ok",
    )

    eps = [r["execution_point"] for r in spine.records]
    assert "phase.perceive.fold" in eps
    assert adapter.cursor.snapshot.phase == "perceive"


def test_adapter_close_triggers_cursor_close_ep() -> None:
    """``adapter.close(reason)`` → cursor.close(reason) 触发 writable.iteration.closing EP。"""
    adapter, spine, _ = _build_adapter()

    adapter.close("completed")

    eps = [r["execution_point"] for r in spine.records]
    assert "writable.iteration.closing" in eps
    closing_ep = next(
        r for r in spine.records if r["execution_point"] == "writable.iteration.closing"
    )
    assert closing_ep["payload"]["reason"] == "completed"


def test_adapter_record_reflect_delegates_to_coord_only() -> None:
    """``adapter.record_reflect(reflect)`` —— cursor 不暴露 record_reflect;仅 coord 写。"""
    adapter, spine, _ = _build_adapter()
    adapter.begin_step("think")

    reflect = ReflectTrace(summary="ok", verdict="ok")
    adapter.record_reflect(reflect)

    # cursor 不知道 record_reflect;spine 不应有 step.reflect.record EP
    eps = [r["execution_point"] for r in spine.records]
    assert "step.reflect.record" not in eps


def test_adapter_record_span_delegates_to_coord_only() -> None:
    """``adapter.record_span(span)`` —— cursor 不暴露 record_span;仅 coord 写。"""
    adapter, spine, _ = _build_adapter()
    adapter.begin_step("think")

    span = SpanRecord(kind="runtime_observed", started_at=0.0)
    adapter.record_span(span)

    eps = [r["execution_point"] for r in spine.records]
    assert "step.span.record" not in eps


def test_adapter_emit_passes_through_to_coord() -> None:
    """``adapter.emit(...)`` —— cursor 不暴露任意 EP 入口;只走 coord。

    StepCoordinator.emit 走五面矩阵(emitter / coalescer / storage),不是
    spine;所以 ``spine.records`` 不会增加(capture 端需走 coord 自身)。
    """
    adapter, spine, _ = _build_adapter()
    adapter.emit(
        execution_point="writable.step.start",
        payload={"phase": "think"},
    )

    # spine 不接收任意 EP —— adapter.emit 不调 spine
    eps = [r["execution_point"] for r in spine.records]
    assert "writable.step.start" not in eps


def test_adapter_exposes_cursor_and_coord() -> None:
    """``adapter.cursor`` / ``adapter.coord`` —— 供 PR-21~24 wiring 切换期使用。"""
    adapter, _, _ = _build_adapter()
    assert isinstance(adapter.cursor, StdLoopCursor)
    assert isinstance(adapter.coord, StepCoordinator)


def test_adapter_run_id_and_trace_id_passthrough() -> None:
    """``adapter.run_id`` / ``adapter.trace_id`` —— 透传 coord(向后兼容)。"""
    adapter, _, _ = _build_adapter()
    assert adapter.run_id == "r1"
    assert adapter.trace_id == "t1"


def test_adapter_unknown_attr_passthrough_to_coord() -> None:
    """未显式代理的属性 → ``__getattr__`` 透传 coord(向后兼容 fixture)。"""
    adapter, _, coord = _build_adapter()
    assert adapter.metadata == coord.metadata


def test_adapter_context_manager_propagates_to_coord() -> None:
    """``with adapter: ...`` —— 进入 context manager 时 coord 也进。"""
    adapter, _, _ = _build_adapter()
    with adapter as inner:
        assert inner is adapter
