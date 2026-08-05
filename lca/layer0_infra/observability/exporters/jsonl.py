"""JSONL 落盘导出器 —— 每行一条 JSON，jq 可查。

行格式（``record`` 区分）：
- ``{"record":"span", ...}``：span 全量字段（trace/span/parent id、属性、耗时）
- ``{"record":"event", ...}``：业务事件（挂在所属 span 下）
- ``{"record":"digest", ...}``：根 span 结束时的运行摘要
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from lca.layer0_infra.observability.view import SpanView, view_of


class JsonlExporter(SpanExporter):
    """将 span/event/digest 以 JSONL 追加写入文件。"""

    def __init__(self, output_path: str | Path = "traces/lca_trace.jsonl") -> None:
        self._path = Path(output_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh: TextIO = self._path.open("a", encoding="utf-8")

    def export(self, spans: Sequence[Any]) -> SpanExportResult:
        for readable in spans:
            view = view_of(readable)
            self._write(self._span_record(view))
            for name, attrs in view.events:
                self._write(
                    {
                        "record": "event",
                        "trace_id": view.trace_id,
                        "span_id": view.span_id,
                        "name": name,
                        "attributes": attrs,
                    }
                )
            if view.parent_span_id is None:
                self._write(
                    {
                        "record": "digest",
                        "trace_id": view.trace_id,
                        "duration_ms": view.duration_ms,
                        "status": view.attributes.get("status", ""),
                    }
                )
        return SpanExportResult.SUCCESS

    @staticmethod
    def _span_record(view: SpanView) -> dict[str, Any]:
        return {
            "record": "span",
            "trace_id": view.trace_id,
            "span_id": view.span_id,
            "parent_span_id": view.parent_span_id,
            "name": view.name,
            "status": view.status,
            "duration_ms": view.duration_ms,
            "attributes": view.attributes,
        }

    def _write(self, record: dict[str, Any]) -> None:
        self._fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        self._fh.flush()

    def shutdown(self) -> None:
        self._fh.close()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        self._fh.flush()
        return True
