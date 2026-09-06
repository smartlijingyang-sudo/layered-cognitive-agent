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

ADR-0194 P2-09: ``record_*`` / ``emit_phase`` / ``emit`` stub 已删除;
spine EP 唯一走 ``LoopCursor`` WritePort (``cursor.advance`` / ``record_*``)。
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from lca.infrastructure.observability.spine.event.record import (
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
    """唯一写入口。Agent 调 driver/segment 状态; spine EP 由 cursor 派生。

    ADR-0167 D11: ``bind_run`` 设置 run 身份 + 元数据; 业务侧只在
    bind 之后才能 begin_step / begin_segment。
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
        now = datetime.now(UTC)
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
        emitter = self.registry.require("emitter")
        coalescer = self.registry.require("coalescer")
        serializer = self.registry.require("serializer")
        storage = self.registry.require("storage")
        emitter.emit(record)
        coalescer.feed(record.execution_point, record.payload)
        storage.write(serializer.serialize(record))

    # ── 切步 / 切段 ────────────────────────────────────────────────

    def begin_step(self, phase: str, **ctx: Any) -> str:
        """SSOT 收口后,begin_step 仅保留 driver 派生 step_id 的内部状态。

        不再写 ``writable.step.start`` EP —— 该显式边界由 cursor 发射:
        ``record_request_header`` / ``open_step``(ADR-0184 D6)。
        业务路径必须走 cursor。
        """
        if self._current_step is not None:
            raise RuntimeError(f"begin_step while step {self._current_step!r} still open")
        driver = self.registry.require("driver")
        step_id = driver.begin_step(phase, **ctx)
        self._current_step = step_id
        return cast("str", step_id)

    def end_step(
        self,
        outcome: str = "success",
        *,
        error: str | None = None,
    ) -> None:
        """仅做 driver.end_step 状态收尾,不再写 ``writable.step.end`` EP。

        该显式边界由 cursor 发射:``advance('stop')`` 与 ``close``
        (ADR-0184 D6)。
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
        segment_id = driver.begin_segment(self._current_step, kind)
        self._current_segment = segment_id
        return cast("str", segment_id)

    def end_segment(self, outcome: str = "success") -> None:
        """仅做 driver.end_segment 状态收尾,不再写 EP。"""
        if self._current_segment is None:
            raise RuntimeError("end_segment while no segment open")
        driver = self.registry.require("driver")
        seg_id = self._current_segment
        driver.end_segment(seg_id, outcome)
        self._current_segment = None

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
