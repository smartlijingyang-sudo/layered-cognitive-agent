"""JSONL 文件可观测性 —— 每条 TraceSpan 序列化为 JSON 追加写入文件。

用于真实 LLM 链路的离线回放排障：
  - 每行一个 JSON 对象，可用 ``jq`` 按 ``trace_id`` 过滤
  - 文件不存在时自动创建
  - 线程安全（文件追加模式，OS 级别原子写入保证行完整性）

用法：
    obs = JSONLFileObservability(output_path="traces/run.jsonl")
    agent = Agent(..., observability=obs)
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from lca.contracts.protocols import Observability

logger = logging.getLogger(__name__)


class JSONLFileObservability(Observability):
    """实现 Observability 协议。将 TraceSpan 以 JSONL 格式落盘。"""

    name = "jsonl_file"

    def __init__(self, output_path: str | Path = "traces/lca_trace.jsonl") -> None:
        self._path = Path(output_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def emit_span(self, span: Any) -> None:
        """将 TraceSpan 序列化为一行 JSON 追加写入文件。"""
        try:
            record = self._serialize_span(span)
            line = json.dumps(record, ensure_ascii=False, default=str)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            logger.exception("Failed to write trace span to %s", self._path)

    def _serialize_span(self, span: Any) -> dict[str, Any]:
        """将 TraceSpan 转为可 JSON 序列化的 dict。"""
        if hasattr(span, "__dataclass_fields__"):
            record = asdict(span)
        elif hasattr(span, "to_dict"):
            record = span.to_dict()
        elif isinstance(span, dict):
            record = dict(span)
        else:
            record = {"span_data": str(span)}

        # 确保 datetime 字段可序列化
        for key, value in record.items():
            if isinstance(value, datetime):
                record[key] = value.isoformat()

        return record

    @property
    def output_path(self) -> Path:
        """返回输出文件路径。"""
        return self._path
