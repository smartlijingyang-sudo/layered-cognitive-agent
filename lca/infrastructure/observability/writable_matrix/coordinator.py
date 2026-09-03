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
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

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
        # SSOT 收口:StepCoordinator 不再是 spine writer。cursor 是唯一写入者
        # (ADR-0169 P2 / D1);此方法保留仅供内部 state 派生(driver.begin_step
        # 仍要走 StepDriver registry 派生 step_id,见 begin_step 注释)。
        # 业务路径(record_* / emit_* / emit_phase)必须改走 cursor。
        emitter = self.registry.require("emitter")
        coalescer = self.registry.require("coalescer")
        serializer = self.registry.require("serializer")
        storage = self.registry.require("storage")
        emitter.emit(record)
        coalescer.feed(record.execution_point, record.payload)
        storage.write(serializer.serialize(record))

    def _block_ep_write(self, ep: str) -> None:
        r"""业务路径 EP 写入 SSOT 守护 —— cursor 才是唯一 writer。

        COMPAT(delete-when: ``rg "step\.thinking\.record\|step\.tool_call\.record\|step\.tool_result\.record\|step\.reflect\.record\|step\.span\.record\|phase\..*\.fold\|writable\.step\|writable\.segment" lca/infrastructure/observability/writable_matrix/coordinator.py`` 仅剩 begin_step/end_step/begin_segment/end_segment 的内部 _write,
        tracking: ADR-0169-task-25)。
        """
        raise NotImplementedError(
            f"StepCoordinator.{ep} 已废弃:spine EP 写入唯一走 cursor.advance / cursor.record_*(SSOT)。"
        )

    # ── 切步 / 切段 ────────────────────────────────────────────────

    def begin_step(self, phase: str, **ctx: Any) -> str:
        """SSOT 收口后,begin_step 仅保留 driver 派生 step_id 的内部状态。

        不再写 ``writable.step.start`` EP —— step 派生由 cursor.record_request_header
        完成(ADR-0169 D4,L6)。业务路径必须走 cursor。
        """
        if self._current_step is not None:
            raise RuntimeError(f"begin_step while step {self._current_step!r} still open")
        driver = self.registry.require("driver")
        self._current_step = driver.begin_step(phase, **ctx)
        return self._current_step

    def end_step(
        self,
        outcome: str = "success",
        *,
        error: str | None = None,
    ) -> None:
        """仅做 driver.end_step 状态收尾,不再写 ``writable.step.end`` EP。

        EP 派生由 cursor.advance('stop') 完成(ADR-0169 P2)。
        """
        if self._current_step is None:
            raise RuntimeError("end_step while no step open")
        driver = self.registry.require("driver")
        step_id = self._current_step
        driver.end_step(step_id, outcome)
        self._current_step = None

    def begin_segment(self, kind: str) -> str:
        """仅做 driver.begin_segment 状态派生,不再写 ``writable.segment.start`` EP。

        EP 由 cursor 派生(ADR-0169)。
        """
        if self._current_step is None:
            raise RuntimeError("begin_segment while no step open")
        driver = self.registry.require("driver")
        self._current_segment = driver.begin_segment(self._current_step, kind)
        return self._current_segment

    def end_segment(self, outcome: str = "success") -> None:
        """仅做 driver.end_segment 状态收尾,不再写 EP。"""
        if self._current_segment is None:
            raise RuntimeError("end_segment while no segment open")
        driver = self.registry.require("driver")
        seg_id = self._current_segment
        driver.end_segment(seg_id, outcome)
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
        """SSOT 守护:任意 EP 入口已废弃 —— 由 cursor 派生。

        COMPAT(见 _block_ep_write 注释)。保留空实现仅供 fixture 旧 wiring
        不破;业务代码必须改用 cursor.advance / cursor.record_*。
        """
        del execution_point, channel, payload, outcome, reason
        self._block_ep_write("emit")

    # ── phase 边（perceive / remember / stop 不开 step）──────────

    def emit_phase(
        self,
        *,
        phase: str,
        objective: str,
        summary: str,
        outcome: str = "ok",
    ) -> None:
        """SSOT 守护:phase.<x>.fold 必须由 cursor.advance 派生。

        COMPAT(见 _block_ep_write 注释)。本方法保留以保旧 wiring 不破,但
        一旦调用即 raise,迫使调用方迁移到 cursor。
        """
        del phase, objective, summary, outcome
        self._block_ep_write("emit_phase")

    # ── record_*(Agent 写原语) ─────────────────────────────────

    def record_thinking(self, trace: ThinkingTrace) -> None:
        """SSOT 守护:step.thinking.record 由 cursor.record_thinking 派生。"""
        del trace
        self._block_ep_write("record_thinking")

    def record_tool_call(self, call: ToolCallRecord) -> None:
        """SSOT 守护:step.tool_call.record 由 cursor.record_tool_call 派生。"""
        del call
        self._block_ep_write("record_tool_call")

    def record_tool_result(self, result: ToolResult) -> None:
        """SSOT 守护:step.tool_result.record 由 cursor.record_tool_result 派生。"""
        del result
        self._block_ep_write("record_tool_result")

    def record_reflect(self, reflect: ReflectTrace) -> None:
        """SSOT 守护:step.reflect.record 由 cursor 派生。"""
        del reflect
        self._block_ep_write("record_reflect")

    def record_span(self, span: SpanRecord) -> None:
        """SSOT 守护:step.span.record 由 cursor 派生。"""
        del span
        self._block_ep_write("record_span")

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
