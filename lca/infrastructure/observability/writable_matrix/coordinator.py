"""StepCoordinator —— Agent 唯一可见的写 API（ADR-0167 D2 / D11）。

Agent / Brain / Body / Perceive 只与 ``StepCoordinator`` 交互。
``StepCoordinator`` 持有 ``WritableFaceRegistry``，把每次「意图」
转换为五面矩阵上的链式调用：Emitter → Driver → Coalescer → Serializer
→ Storage。

链上每节都可独立替换（I-PLUG3）；Coordinator 自身永不 import 任何具体
实现，永远通过 Protocol + registry 解引用（I-PLUG1）。

禁止（ADR-0167 D13 设计尊严）：
- 缓存默认值 / 未配置就抛错的伪防御
- 重复 emit 同一事实（D9 I-PLUG3）；上游 deriver 仅订阅一次
- 「过渡期两边同时写」层——全部在 PR-3 一次性切
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, get_args

from lca.contracts.models.observability.journal_step import (
    ReflectTrace,
    SpanRecord,
    ThinkingTrace,
    ToolCallRecord,
    ToolResult,
)
from lca.infrastructure.observability.spine.event_record import (
    Channel,
    EventRecord,
    Outcome,
    Phase,
)
from lca.infrastructure.observability.writable_matrix.registry import (
    MissingWritableFaceError,
    WritableFaceRegistry,
)

_current: ContextVar[StepCoordinator | None] = ContextVar("lca_writable_coordinator", default=None)


def get_current_coordinator() -> StepCoordinator | None:
    """运行时取当前协程/任务绑定的 Coordinator。

    未注入返回 ``None`` —— 调用方应让 Agent 显式持有一个 coordinator，
    而不是依赖 ContextVar 隐藏的全局状态（ADR-0167 D13 / B10 反对
    「隐式全局副作用」）。
    """
    return _current.get()


def bind_current_coordinator(coord: StepCoordinator) -> Any:
    """绑定 coordinator；返回 reset token，由调用方在 finally 释放。"""
    return _current.set(coord)


def reset_current_coordinator(token: Any) -> None:
    _current.reset(token)


@dataclass
class StepCoordinator:
    """唯一写入口。Agent 调 ``emit_*``，由 Coordinator 走五面矩阵。

    ADR-0167 D11: ``bind_run`` 设置 run 身份 + 元数据; 业务侧只在
    bind 之后才能 begin_step / record_*。
    """

    registry: WritableFaceRegistry
    run_id: str = "default-run"
    trace_id: str = ""
    metadata: Any = None  # JournalMetadata
    started_at: float | None = None
    _current_step: str | None = None
    _current_segment: str | None = None
    _seq: int = 0

    def bind_run(
        self,
        *,
        run_id: str,
        trace_id: str,
        metadata: Any,
        started_at: float | None = None,
    ) -> None:
        """绑定 run 身份。bind 不发 EP(state 已就位; 与旧 StepLifecycleStore 一致)。"""
        self.run_id = run_id
        self.trace_id = trace_id
        self.metadata = metadata
        self.started_at = started_at

    def _mint_record(
        self,
        *,
        execution_point: str,
        channel: Channel = "fact",
        payload: dict[str, Any] | None = None,
        outcome: Outcome | None = None,
        phase: Phase = "live",
        reason: str | None = None,
    ) -> EventRecord:
        self._seq += 1
        now = datetime.now(timezone.utc)
        return EventRecord(
            execution_point=execution_point,
            channel=channel,
            span_id=f"coord-{self._seq:06x}",
            parent_span_id=None,
            sequence=self._seq,
            epoch=1,
            causality_id=f"caus-{self._seq:06x}",
            outcome=outcome,
            when=now,
            when_corrected=now,
            prev_event_hash=None,
            run_id=self.run_id,
            step_id=self._current_step,
            payload=payload or {},
            phase=phase,
            reason=reason,
        )

    def _write(self, record: EventRecord) -> None:
        emitter = self.registry.require("emitter")
        coalescer = self.registry.require("coalescer")
        serializer = self.registry.require("serializer")
        storage = self.registry.require("storage")
        emitter.emit(record)
        coalescer.feed(record.execution_point, record.payload)
        storage.write(serializer.serialize(record))

    # ── 切步 / 切段 ────────────────────────────────────────────────

    def begin_step(self, phase: str, **ctx: Any) -> str:
        if self._current_step is not None:
            raise RuntimeError(f"begin_step while step {self._current_step!r} still open")
        driver = self.registry.require("driver")
        self._current_step = driver.begin_step(phase, **ctx)
        self._write(
            self._mint_record(
                execution_point="writable.step.start",
                payload={"phase": phase, "step_id": self._current_step, **ctx},
            )
        )
        return self._current_step

    def end_step(
        self,
        outcome: str = "success",
        *,
        error: str | None = None,
    ) -> None:
        if self._current_step is None:
            raise RuntimeError("end_step while no step open")
        driver = self.registry.require("driver")
        step_id = self._current_step
        driver.end_step(step_id, outcome)
        payload: dict[str, Any] = {"step_id": step_id, "outcome": outcome}
        if error is not None:
            payload["error"] = error
        final_outcome: str = "failure" if error is not None else outcome
        self._write(
            self._mint_record(
                execution_point="writable.step.end",
                payload=payload,
                outcome=final_outcome,
            )
        )
        self._current_step = None

    def begin_segment(self, kind: str) -> str:
        if self._current_step is None:
            raise RuntimeError("begin_segment while no step open")
        driver = self.registry.require("driver")
        self._current_segment = driver.begin_segment(self._current_step, kind)
        self._write(
            self._mint_record(
                execution_point="writable.segment.start",
                payload={
                    "step_id": self._current_step,
                    "segment_id": self._current_segment,
                    "kind": kind,
                },
            )
        )
        return self._current_segment

    def end_segment(self, outcome: str = "success") -> None:
        if self._current_segment is None:
            raise RuntimeError("end_segment while no segment open")
        driver = self.registry.require("driver")
        seg_id = self._current_segment
        driver.end_segment(seg_id, outcome)
        self._write(
            self._mint_record(
                execution_point="writable.segment.end",
                payload={"segment_id": seg_id, "outcome": outcome},
                outcome=outcome,
            )
        )
        self._current_segment = None

    # ── 通用 emit ─────────────────────────────────────────────────

    def emit(
        self,
        *,
        execution_point: str,
        channel: Channel = "fact",
        payload: dict[str, Any] | None = None,
        outcome: Outcome | None = None,
        reason: str | None = None,
    ) -> None:
        """任意 EP 入口；delegate 给五面矩阵。"""
        self._write(
            self._mint_record(
                execution_point=execution_point,
                channel=channel,
                payload=payload,
                outcome=outcome,
                reason=reason,
            )
        )

    # ── phase 边（perceive / remember / stop 不开 step）──────────

    def emit_phase(
        self,
        *,
        phase: str,
        objective: str,
        summary: str,
        outcome: str = "ok",
    ) -> None:
        """不开 step 的相位：单次事实事件（ADR-0167 D2 / D11）。

        ADR-0166 D4：perceive / reflect / remember / stop 不创建 step，
        写入 ``phase.<name>.fold`` 一个事实 EP；stop 与失败回退由
        Driver 在 ``end_step`` 处表达。
        """
        outcome_lit = outcome if outcome in get_args(Outcome) else None
        self._write(
            self._mint_record(
                execution_point=f"phase.{phase}.fold",
                payload={
                    "phase": phase,
                    "objective": objective,
                    "summary": summary,
                },
                outcome=outcome_lit,
            )
        )

    # ── record_*(Agent 写原语) ─────────────────────────────────

    def record_thinking(self, trace: ThinkingTrace) -> None:
        if self._current_step is None:
            raise RuntimeError("record_thinking: no open step")
        self._write(
            self._mint_record(
                execution_point="step.thinking.record",
                payload={"trace": asdict(trace)},
            )
        )

    def record_tool_call(self, call: ToolCallRecord) -> None:
        if self._current_step is None:
            raise RuntimeError("record_tool_call: no open step")
        self._write(
            self._mint_record(
                execution_point="step.tool_call.record",
                payload={"call": asdict(call)},
            )
        )

    def record_tool_result(self, result: ToolResult) -> None:
        if self._current_step is None:
            raise RuntimeError("record_tool_result: no open step")
        self._write(
            self._mint_record(
                execution_point="step.tool_result.record",
                payload={"result": asdict(result)},
                outcome="success" if result.ok else "failure",
            )
        )

    def record_reflect(self, reflect: ReflectTrace) -> None:
        if self._current_step is None:
            raise RuntimeError("record_reflect: no open step")
        self._write(
            self._mint_record(
                execution_point="step.reflect.record",
                payload={"reflect": asdict(reflect)},
            )
        )

    def record_span(self, span: SpanRecord) -> None:
        if self._current_step is None:
            raise RuntimeError("record_span: no open step")
        self._write(
            self._mint_record(
                execution_point="step.span.record",
                payload={"span": asdict(span)},
            )
        )

    # ── context manager 便利 ─────────────────────────────────────

    def __enter__(self) -> StepCoordinator:
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._current_segment is not None:
            self.end_segment("cancelled")
        if self._current_step is not None:
            self.end_step("cancelled")


__all__ = [
    "MissingWritableFaceError",
    "StepCoordinator",
    "bind_current_coordinator",
    "get_current_coordinator",
    "reset_current_coordinator",
]
