"""journal 持久化 I/O —— schema 版本化的序列化/反序列化（ADR-0037）。

record-as-data：执行日志是主数据，落盘格式版本化（``journal.v1``），
replay 从文件重建事件流投给任意投影器（console/OTel/序列图），
对齐 LobeHub「过程即数据库记录」范式。

行格式::

    {"schema": "journal.v1", "seq": 1, "ts": 17123.45,
     "scope": {"trace_id", "run_id", "parent_run_id", "delegation_id", "agent_role"},
     "event_type": "DelegationIssued", "event": {...}}

前向兼容：未知 event_type 反序列化返回 None（replay 跳过而非崩溃）。
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from lca.contracts.models.observability.journal import (
    RunScope,
    StampedEvent,
)
from lca.contracts.models.observability.journal_catalog import JOURNAL_EVENT_CLASSES

JOURNAL_SCHEMA_VERSION = "journal.v1"


class JournalFormatError(ValueError):
    """journal 行格式非法（schema 版本不符 / JSON 损坏）。"""


def stamped_to_record(stamped: StampedEvent) -> dict[str, Any]:
    """StampedEvent → JSON-serializable record.

    Spec §24.5 / Phase J: ``event_type``, ``data``, ``turn`` and
    ``correlation_ids`` are emitted so the durable journal carries
    the full Phase J schema.
    """
    return {
        "schema": JOURNAL_SCHEMA_VERSION,
        "seq": stamped.seq,
        "ts": stamped.ts,
        "scope": dataclasses.asdict(stamped.scope),
        "event_type": stamped.event_type or type(stamped.event).__name__,
        "turn": stamped.turn,
        "data": dict(stamped.data),
        "correlation_ids": list(stamped.correlation_ids),
        "event": dataclasses.asdict(stamped.event),
    }


def record_to_stamped(record: dict[str, Any]) -> StampedEvent | None:
    """record → StampedEvent；未知事件类型返回 None（前向兼容）。"""
    schema = record.get("schema")
    if schema != JOURNAL_SCHEMA_VERSION:
        raise JournalFormatError(f"不支持的 journal schema：{schema!r}")
    event_cls = JOURNAL_EVENT_CLASSES.get(record.get("event_type", ""))
    if event_cls is None:
        return None
    event = event_cls(**record.get("event", {}))
    scope = RunScope(**record.get("scope", {}))
    return StampedEvent(
        seq=record.get("seq", 0),
        ts=record.get("ts", 0.0),
        scope=scope,
        event=event,
        turn=int(record.get("turn", 0) or 0),
        event_type=str(record.get("event_type", "") or type(event).__name__),
        data=dict(record.get("data", {}) or {}),
        correlation_ids=tuple(record.get("correlation_ids", ()) or ()),
    )


def read_journal(path: str | Path) -> list[StampedEvent]:
    """读取 jsonl journal 文件 → 事件流（损坏行抛 JournalFormatError）。"""
    events: list[StampedEvent] = []
    file_path = Path(path)
    for line_number, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as err:
            raise JournalFormatError(f"{file_path}:{line_number} JSON 损坏：{err}") from err
        stamped = record_to_stamped(record)
        if stamped is not None:
            events.append(stamped)
    return events
