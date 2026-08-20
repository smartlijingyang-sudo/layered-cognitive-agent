"""运行诊断流及其本地 JSONL 接收器（ADR-0063）。

此模块只处理非事实诊断事件。Journal 的写入、重放和 reducer 完全不依赖它；
诊断接收器故障被隔离，绝不能影响 agent run。
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import TextIO

import structlog

from lca.contracts.models.observability.diagnostic import DiagnosticEvent
from lca.contracts.protocols import DiagnosticSink

_log = structlog.get_logger("lca.diagnostics")


class _IsolatedDiagnosticSink(DiagnosticSink):
    """隔离单个诊断接收器的故障，沿用 Journal/OTel 的不阻断原则。"""

    def __init__(self, inner: DiagnosticSink) -> None:
        self._inner = inner

    @property
    def inner(self) -> DiagnosticSink:
        return self._inner

    def on_event(self, event: DiagnosticEvent) -> None:
        try:
            self._inner.on_event(event)
        except Exception:
            _log.warning(
                "diagnostic_sink_failed",
                sink=type(self._inner).__name__,
                operation=event.operation,
            )

    def flush(self) -> None:
        try:
            self._inner.flush()
        except Exception:
            _log.warning("diagnostic_sink_flush_failed", sink=type(self._inner).__name__)

    def close(self) -> None:
        try:
            self._inner.close()
        except Exception:
            _log.warning("diagnostic_sink_close_failed", sink=type(self._inner).__name__)


class DiagnosticStream:
    """诊断事件的顺序扇出器；不持久化、也不拥有领域事实。"""

    def __init__(self, sinks: tuple[DiagnosticSink, ...] = ()) -> None:
        self._sinks = [_IsolatedDiagnosticSink(sink) for sink in sinks]
        self._sequence = 0
        self._closed = False

    @property
    def sinks(self) -> tuple[DiagnosticSink, ...]:
        return tuple(sink.inner for sink in self._sinks)

    def emit(self, event: DiagnosticEvent) -> DiagnosticEvent:
        if self._closed:
            return event
        self._sequence += 1
        stamped = dataclasses.replace(event, seq=self._sequence)
        for sink in self._sinks:
            sink.on_event(stamped)
        return stamped

    def flush(self) -> None:
        for sink in self._sinks:
            sink.flush()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.flush()
        for sink in self._sinks:
            sink.close()


class JsonlDiagnosticSink(DiagnosticSink):
    """每行一个版本化 ``DiagnosticEvent`` 的 run-scoped JSONL 接收器。"""

    def __init__(self, output_path: str | Path) -> None:
        self._path = Path(output_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh: TextIO = self._path.open("a", encoding="utf-8")
        self._closed = False

    @property
    def path(self) -> Path:
        return self._path

    def on_event(self, event: DiagnosticEvent) -> None:
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


__all__ = ["DiagnosticStream", "JsonlDiagnosticSink"]
