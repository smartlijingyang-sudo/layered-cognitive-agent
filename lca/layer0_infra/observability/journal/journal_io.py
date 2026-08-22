"""journal 持久化 I/O —— ADR-0065 §三 / §四 / PR-3 disk-format flip。

record-as-data:执行日志是主数据,落盘格式版本化(``lca.journal/2``),
replay 从文件重建事件流投给任意投影器(console / OTel / 序列图 /
Coding Agent tools)。

**PR-3 disk-format flip** —— 本模块是 journal 边界的唯一切换点:

* ``stamped_to_record`` 把 ``StampedEvent`` 序列化成 ``lca.journal/2``
  envelope,派生 ``event_id`` 确定性 hash,落 ``Causation.parent_event_id``,
  strip ADR §四 view-only 字段(``*_preview`` / ``output_truncated`` /
  ``plugin_state``),带 ``EvidenceRef`` 引用。
* ``record_normalize`` idempotently 把 v1 / v2 字典升级到 v2 envelope。
* ``record_to_stamped`` 把任何 v2 record 重建为 ``StampedEvent``,
  unknown descriptor.type 返回 None(replay 跳过而非崩溃)。
* ``read_journal`` 两遍扫描:第一遍收集 ``event_id → run_seq`` 映射,
  第二遍构造 ``StampedEvent`` 时正确还原 ``parent_seq``。

**In-memory 不变**(0065 L1 / ADR §三):``StampedEvent`` 仍为内存层
canonical 类型,view-only 字段在内存中保留供 projector 视图构造;
disk v2 envelope 仅存 typed facts。
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from lca.contracts.models.observability.journal import (
    JournalEvent,
    JournalRecord,
    RunScope,
    StampedEvent,
)
from lca.contracts.models.observability.journal_catalog import (
    JOURNAL_EVENT_CLASSES,
)
from lca.layer0_infra.observability.journal.serialization import (
    stamped_to_journal_record,
)

# ── Schema 常量 ─────────────────────────────────────────────────────

V1_SCHEMA = "journal.v1"
"""Legacy schema tag emitted before PR-3 disk-format flip。读路径兼容;写路径已不再产 v1。"""

V2_SCHEMA = "lca.journal/2"
"""Current canonical schema (ADR-0065 §三)。所有 emit 路径都产 v2。"""

JOURNAL_SCHEMA_VERSION = V2_SCHEMA
"""当前 emit 的 schema tag(PR-3 后固定为 v2)。"""

_LEGACY_SCHEMA_TAGS = frozenset({V1_SCHEMA, "lca.journal/1"})
"""读路径接受的 legacy schema tag 集合;不在这里的一律 fail-fast。"""

# ── 字段识别辅助 ──────────────────────────────────────────────────


def _is_view_only_field(field_name: str) -> bool:
    """Return True for ADR-0065 §四 view-only fields (NOT journal facts).

    Per §四: ``*_preview`` / ``result_preview`` / ``output_truncated`` /
    ``plugin_state`` 不再作为账本事实字段。dataclass 中保留供 in-memory
    projector 使用,但 emit 时从 disk v2 envelope ``data`` 字段剥离。
    """
    if field_name in {"output_truncated", "plugin_state"}:
        return True
    return field_name.endswith("_preview")


def _strip_view_only_data(
    data: Mapping[str, Any],
    event_type: type[JournalEvent],
) -> dict[str, Any]:
    """Remove ADR-0065 §四 view-only fields from a payload dict for disk write.

    Strips top-level fields whose dataclass name matches the view-only set,
    and recursively strips the same key set from ``attributes`` /
    ``output`` sub-dicts (RuntimeObserved carriers). The in-memory
    StampedEvent keeps these fields for projector use; only the disk-bound
    v2 envelope loses them.
    """
    if not data:
        return {}
    strip_top: set[str] = {
        f.name for f in dataclasses.fields(event_type) if _is_view_only_field(f.name)
    }
    strip_subkeys = {"attributes", "output"}
    out: dict[str, Any] = {}
    for key, value in data.items():
        if key in strip_top:
            continue
        if key in strip_subkeys and isinstance(value, dict):
            out[key] = {k: v for k, v in value.items() if not _is_view_only_field(str(k))}
            continue
        out[key] = value
    return out


# ── event_id 派生 ──────────────────────────────────────────────────


def _derive_event_id(
    *,
    run_id: str,
    run_seq: int,
    event_type: str,
    ts: float,
) -> str:
    """Deterministic event_id (ADR-0065 §三 / L3)。

    - 同一 ``(run_id, run_seq, event_type, ts)`` 永远产同一 event_id;
      replay / re-emit 稳定,causation.parent_event_id 可跨重放解析。
    - 跨 run 唯一(``run_id` 是 ULID)。
    - 24 hex chars + ``evt_`` 前缀 = 28 字符,落入工程惯例。
    """
    material = f"{run_id}|{run_seq}|{event_type}|{ts:.6f}".encode()
    return "evt_" + hashlib.sha256(material).hexdigest()[:24]


# ── 序列化主路径 ──────────────────────────────────────────────────


def stamped_to_record(stamped: StampedEvent) -> dict[str, Any]:
    """StampedEvent → v2 envelope record(ADR-0065 §三 / §四 / PR-3)。

    新 emit 永远产 v2 envelope;``run_id`` 取 ``stamped.scope.run_id``;
    ``parent_event_id`` 由 engine.append 在 ledger 单临界区里填,这里透传。
    typed fields(code / language / command / skill_id / ...)从
    ``stamped.data`` 提取后保留,view-only 字段从 ``data`` 剥离;
    disk 写入只存 typed facts(0065 §四 L1)。

    ``event_id`` 优先取 ``stamped.event_id``(engine 在 append 时注入),
    否则按 ``(run_id, run_seq, event_type, ts)`` 派生确定。
    """
    event_type = stamped.event_type or type(stamped.event).__name__
    run_id = str(stamped.scope.run_id)
    occurred = float(stamped.ts)
    committed = float(stamped.ts)
    payload_data: dict[str, Any] = dict(stamped.data)
    if not payload_data:
        try:
            payload_data = dict(dataclasses.asdict(stamped.event))
        except (TypeError, ValueError):
            payload_data = {}
    # ADR-0065 §四: strip view-only fields from disk-bound data
    payload_data = _strip_view_only_data(payload_data, type(stamped.event))
    event_id = stamped.event_id or _derive_event_id(
        run_id=run_id,
        run_seq=stamped.seq,
        event_type=event_type,
        ts=occurred,
    )
    record = stamped_to_journal_record(
        stamped,
        event_id=event_id,
        run_id=run_id,
        run_seq=stamped.seq,
        occurred_at=occurred,
        committed_at=committed,
        descriptor_version=1,
        payload_schema_version=1,
    )
    if payload_data:
        record = dataclasses.replace(record, data=payload_data)
    if not record.descriptor.type:
        record = dataclasses.replace(
            record,
            descriptor=dataclasses.replace(record.descriptor, type=event_type),
        )
    if stamped.parent_event_id:
        record = dataclasses.replace(
            record,
            causation=dataclasses.replace(
                record.causation, parent_event_id=stamped.parent_event_id
            ),
        )
    return record.to_dict()


def record_normalize(record: Mapping[str, Any]) -> dict[str, Any]:
    """Idempotently normalize any record to v2 envelope dict。

    - v2 records pass through(浅拷贝,避免下游污染原对象)。
    - v1 records get envelope fields added:``schema`` / ``event_id`` /
      ``run_seq`` / ``occurred_at`` / ``committed_at`` / ``causation`` /
      ``evidence``;``scope`` / ``data`` / ``event_type`` 原样保留;
      legacy ``event`` dict 合并到 ``data``(view-only 字段保留,
      replay 后由 projector 决定如何过滤)。
    - 未知 schema:原样返回(调用方可决定是否跳过)。
    """
    schema = record.get("schema")
    if schema == V2_SCHEMA:
        return dict(record)
    if schema in _LEGACY_SCHEMA_TAGS:
        return _v1_to_v2_record(record)
    return dict(record)


def _v1_to_v2_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """v1 → v2 envelope 升级。``event_id`` 不可还原(派生确定);
    ``parent_event_id`` v1 缺失,留空(causation 在 migration 工具中
    仅在同 ledger 内可解析时由 caller 注入)。"""
    scope_raw = record.get("scope", {}) or {}
    scope = {
        "trace_id": str(scope_raw.get("trace_id", "")),
        "run_id": str(scope_raw.get("run_id", "")),
        "parent_run_id": scope_raw.get("parent_run_id"),
        "parent_trace_id": scope_raw.get("parent_trace_id"),
        "delegation_id": scope_raw.get("delegation_id"),
        "agent_role": str(scope_raw.get("agent_role", "")),
        "step": int(scope_raw.get("step", 0)),
    }
    run_id = scope["run_id"]
    seq = int(record.get("seq", 0))
    ts = float(record.get("ts", 0.0))
    event_type = str(record.get("event_type", "UnknownEvent"))
    event_id = str(record.get("event_id", "")) or _derive_event_id(
        run_id=run_id,
        run_seq=seq,
        event_type=event_type,
        ts=ts,
    )
    # v1 records carry payload in `event` (frozen dataclass asdict) and an
    # optional auxiliary dict in `data`. v2 envelope collapses both into a
    # single `data` field; if `data` is empty we fall back to `event` so
    # call-site payloads survive the migration.
    legacy_data = record.get("data", {}) or {}
    legacy_event = record.get("event", {}) or {}
    merged_data: dict[str, Any] = dict(legacy_data) if legacy_data else dict(legacy_event)
    return {
        "schema": V2_SCHEMA,
        "event_id": event_id,
        "run_id": run_id,
        "run_seq": seq,
        "occurred_at": ts,
        "committed_at": ts,
        "scope": scope,
        "causation": {
            "parent_event_id": str(record.get("parent_event_id", "")),
            "links": list(record.get("causation_links", []) or []),
        },
        "descriptor": {
            "type": event_type,
            "version": 1,
            "payload_schema_version": 1,
        },
        "data": merged_data,
        "evidence": list(record.get("evidence", []) or []),
    }


def record_to_stamped(
    record: Mapping[str, Any],
    *,
    event_id_to_seq: Mapping[str, int] | None = None,
) -> StampedEvent | None:
    """v1 / v2 record → StampedEvent (内存层 bridge,PR-3 兼容层)。

    - v2 envelope 直接构造 ``StampedEvent``,``parent_seq`` 通过
      ``event_id_to_seq`` 反查 ``causation.parent_event_id`` 获得;
      ``run_seq`` → ``seq`` / ``occurred_at`` → ``ts``。
    - v1 records 经 ``record_normalize`` 升级后同样路径。
    - 未知 ``descriptor.type`` 返回 ``None``(前向兼容:replay 跳过)。
    - typed field ``state_ref`` 在 disk v2 envelope 中以 dict 形式存储
      (jsonl),``record_to_stamped`` 重建为 ``EvidenceRef`` 实例(0065 §四 L5)。
    """
    from lca.contracts.observability.evidence import EvidenceRef as _EvidenceRef

    normalized = record_normalize(record)
    if normalized.get("schema") != V2_SCHEMA:
        return None
    descriptor = normalized.get("descriptor", {}) or {}
    event_type = str(descriptor.get("type", "UnknownEvent"))
    event_cls = JOURNAL_EVENT_CLASSES.get(event_type)
    if event_cls is None:
        return None
    scope_payload = normalized.get("scope", {}) or {}
    scope = RunScope(
        trace_id=str(scope_payload.get("trace_id", "")),
        run_id=str(scope_payload.get("run_id", "")),
        parent_run_id=scope_payload.get("parent_run_id"),
        parent_trace_id=scope_payload.get("parent_trace_id"),
        delegation_id=scope_payload.get("delegation_id"),
        agent_role=str(scope_payload.get("agent_role", "")),
        step=int(scope_payload.get("step", 0)),
    )
    data = dict(normalized.get("data", {}) or {})
    # state_ref dict → EvidenceRef (0065 §四 L5 typed field)
    if "state_ref" in data and isinstance(data["state_ref"], dict):
        try:
            data["state_ref"] = _EvidenceRef.from_dict(data["state_ref"])
        except (ValueError, TypeError, KeyError):
            data["state_ref"] = None
    try:
        event = event_cls(**data) if dataclasses.is_dataclass(event_cls) else JournalEvent()
    except (TypeError, ValueError):
        event = JournalEvent()
    causation = normalized.get("causation", {}) or {}
    parent_event_id = str(causation.get("parent_event_id", ""))
    parent_seq: int | None = None
    if event_id_to_seq and parent_event_id:
        parent_seq = event_id_to_seq.get(parent_event_id)
    return StampedEvent(
        seq=int(normalized.get("run_seq", 0)),
        ts=float(normalized.get("occurred_at", 0.0)),
        scope=scope,
        event=event,
        event_type=event_type,
        data=data,
        parent_seq=parent_seq,
        event_id=str(normalized.get("event_id", "")),
        parent_event_id=parent_event_id,
    )


def record_to_journal_record(record: Mapping[str, Any]) -> JournalRecord | None:
    """v1 / v2 record → ``JournalRecord``(无 schema 信息丢失)。

    适用于 inspector / migration 工具,需要保留 envelope 全字段(``evidence``、
    ``causation.links`` 等)的场景。未知 ``descriptor.type`` 不阻塞(因
    ``JournalRecord`` 不绑定 payload class);只校验 schema tag 已知。
    """
    normalized = record_normalize(record)
    if normalized.get("schema") != V2_SCHEMA:
        return None
    return JournalRecord.from_dict(normalized)


def read_journal(path: str | Path) -> list[StampedEvent]:
    """读取 jsonl journal 文件 → ``StampedEvent`` 流。

    两遍扫描:
    1. 先全部解析为 v2 envelope dict,收集 ``event_id → run_seq`` 映射。
    2. 再以映射为上下文构造 ``StampedEvent``,``parent_seq`` 精确解析。

    损坏 JSON 行抛 ``JournalFormatError``;未知 ``descriptor.type`` 在
    第二遍返回 ``None`` 并跳过(前向兼容)。
    """
    file_path = Path(path)
    raw_records: list[dict[str, Any]] = []
    for line_number, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as err:
            raise JournalFormatError(f"{file_path}:{line_number} JSON 损坏:{err}") from err
        raw_records.append(payload)

    # Pass 1: 收集 event_id → seq 映射(供 causation 解析)
    event_id_to_seq: dict[str, int] = {}
    for payload in raw_records:
        normalized = record_normalize(payload)
        if normalized.get("schema") != V2_SCHEMA:
            continue
        event_id = str(normalized.get("event_id", ""))
        if event_id:
            event_id_to_seq[event_id] = int(normalized.get("run_seq", 0))

    # Pass 2: 构造 StampedEvent
    events: list[StampedEvent] = []
    for payload in raw_records:
        stamped = record_to_stamped(payload, event_id_to_seq=event_id_to_seq)
        if stamped is not None:
            events.append(stamped)
    return events


class JournalFormatError(ValueError):
    """journal 行格式非法(schema 版本不符 / JSON 损坏)。"""


__all__ = [
    "JOURNAL_SCHEMA_VERSION",
    "V1_SCHEMA",
    "V2_SCHEMA",
    "JournalFormatError",
    "read_journal",
    "record_normalize",
    "record_to_journal_record",
    "record_to_stamped",
    "stamped_to_record",
]
