"""运行解释事件的 JSONL 兼容投影。

运行解释已写入主事件账本；本模块只把 ``RuntimeObserved`` 渲染成既有
``lca.diagnostic.v1`` JSONL，以便 CLI 和已有运维脚本平滑读取。它不再拥有
独立序列、独立扇出器或独立事实流。
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import TextIO

import structlog

from lca.contracts.models.observability.diagnostic import (
    DiagnosticCategory,
    DiagnosticEvent,
    DiagnosticStatus,
)
from lca.contracts.models.observability.event import OperationOutcome, RuntimeKind
from lca.contracts.models.observability.journal import RuntimeObserved, StampedEvent
from lca.contracts.protocols import DiagnosticSink, JournalProjector

_log = structlog.get_logger("lca.diagnostics")

_CATEGORY_BY_KIND: dict[RuntimeKind, DiagnosticCategory] = {
    RuntimeKind.AGENT: DiagnosticCategory.AGENT,
    RuntimeKind.PLUGIN: DiagnosticCategory.PLUGIN,
    RuntimeKind.HOOK: DiagnosticCategory.HOOK,
    RuntimeKind.LLM: DiagnosticCategory.LLM,
    RuntimeKind.TOOL: DiagnosticCategory.TOOL,
    RuntimeKind.MEMORY: DiagnosticCategory.MEMORY,
    RuntimeKind.TRANSPORT: DiagnosticCategory.TRANSPORT,
    RuntimeKind.CODE: DiagnosticCategory.INFRA,
    RuntimeKind.PERMISSION: DiagnosticCategory.INFRA,
    RuntimeKind.COMPACTION: DiagnosticCategory.INFRA,
    RuntimeKind.ERROR: DiagnosticCategory.INFRA,
    RuntimeKind.RETRY: DiagnosticCategory.INFRA,
}

_STATUS_BY_OUTCOME: dict[OperationOutcome, DiagnosticStatus] = {
    OperationOutcome.STARTED: DiagnosticStatus.STARTED,
    OperationOutcome.OK: DiagnosticStatus.SUCCEEDED,
    OperationOutcome.ERROR: DiagnosticStatus.FAILED,
    OperationOutcome.CANCELLED: DiagnosticStatus.FAILED,
    OperationOutcome.RETRY: DiagnosticStatus.INFO,
}


class DiagnosticJsonlProjection(JournalProjector):
    """把统一账本中的运行解释渲染为旧诊断 JSONL 格式。"""

    def __init__(self, sinks: tuple[DiagnosticSink, ...] = ()) -> None:
        self._sinks = tuple(sinks)
        self._closed = False

    def on_event(self, stamped: StampedEvent) -> None:
        if self._closed or not isinstance(stamped.event, RuntimeObserved):
            return
        event = stamped.event
        for sink in self._sinks:
            try:
                sink.write(
                    DiagnosticEvent(
                        seq=stamped.seq,
                        ts=stamped.ts,
                        run_id=str(stamped.scope.run_id),
                        trace_id=str(stamped.scope.trace_id),
                        parent_run_id=(
                            str(stamped.scope.parent_run_id)
                            if stamped.scope.parent_run_id
                            else None
                        ),
                        delegation_id=stamped.scope.delegation_id,
                        actor=stamped.scope.agent_role,
                        step=stamped.scope.step,
                        category=_CATEGORY_BY_KIND.get(
                            RuntimeKind(event.kind), DiagnosticCategory.INFRA
                        ),
                        operation=event.operation,
                        plugin=event.source,
                        status=_STATUS_BY_OUTCOME.get(
                            OperationOutcome(event.outcome), DiagnosticStatus.INFO
                        ),
                        duration_ms=event.duration_ms,
                        attributes=event.attributes,
                        output=event.output,
                        error_type=event.error_code,
                        error_message=event.error_message,
                        causation_refs=tuple(f"journal:{seq}" for seq in event.causation_refs),
                    )
                )
            except Exception:
                _log.warning(
                    "diagnostic_projection_failed",
                    sink=type(sink).__name__,
                    operation=event.operation,
                    seq=stamped.seq,
                )

    def flush(self) -> None:
        for sink in self._sinks:
            try:
                sink.flush()
            except Exception:
                _log.warning("diagnostic_sink_flush_failed", sink=type(sink).__name__)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.flush()
        for sink in self._sinks:
            try:
                sink.close()
            except Exception:
                _log.warning("diagnostic_sink_close_failed", sink=type(sink).__name__)


class JsonlDiagnosticSink(DiagnosticSink):
    """每行一个诊断兼容记录的本地 JSONL 接收器。"""

    def __init__(self, output_path: str | Path) -> None:
        self._path = Path(output_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh: TextIO = self._path.open("a", encoding="utf-8")
        self._closed = False

    @property
    def path(self) -> Path:
        return self._path

    def write(self, event: DiagnosticEvent) -> None:
        if self._closed:
            return
        self._fh.write(json.dumps(dataclasses.asdict(event), ensure_ascii=False) + "\n")
        self._fh.flush()

    def flush(self) -> None:
        if not self._closed:
            self._fh.flush()

    def close(self) -> None:
        if self._closed:
            return
        self._fh.flush()
        self._fh.close()
        self._closed = True


__all__ = ["DiagnosticJsonlProjection", "JsonlDiagnosticSink"]
