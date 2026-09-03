"""journal 持久化 I/O —— ADR-0065 §三 / ADR-0101 PR-2 disk-format flip。

record-as-data:执行日志是主数据,落盘格式版本化(``lca.journal/2``),
replay 从文件重建事件流投给任意投影器(console / OTel / 序列图 /
Coding Agent tools)。

**PR-3 disk-format flip** —— 本模块是 journal 边界的唯一切换点:

* ``stamped_to_record`` 把 ``StampedEvent`` 序列化成 ``lca.journal/2``
  envelope,带 ``EvidenceRef`` 引用;ADR-0101 PR-2 后,tool 事件
  dataclass 自身只携带事实字段(arguments / arguments_ref / output_ref),
  无 view-only 噪声,``stamped_to_record`` 不再做字段剥离。
* ``record_normalize`` idempotently 把 v1 / v2 字典升级到 v2 envelope。
* ``record_to_stamped`` 把任何 v2 record 重建为 ``StampedEvent``,
  unknown descriptor.type 返回 None(replay 跳过而非崩溃)。
* ``read_journal`` 两遍扫描:第一遍收集 ``event_id → run_seq`` 映射,
  第二遍构造 ``StampedEvent`` 时正确还原 ``parent_seq``。

**In-memory 不变**(0065 L1 / ADR §三):``StampedEvent`` 仍为内存层
canonical 类型;disk v2 envelope 仅存事实字段(typed facts 与 ref)。
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Iterator, Mapping
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
from lca.infrastructure.observability.journal.engine.serialization import (
    stamped_to_journal_record,
)
from lca.plugins.providers.journal_schema.v2 import EnvelopeV2Schema

_DEFAULT_SCHEMA = EnvelopeV2Schema()

# ── Schema 常量 ─────────────────────────────────────────────────────

V1_SCHEMA = "journal.v1"
"""Legacy schema tag emitted before PR-3 disk-format flip。读路径兼容;写路径已不再产 v1。"""

V2_SCHEMA = "lca.journal/2"
"""Current canonical schema (ADR-0065 §三)。所有 emit 路径都产 v2。"""

JOURNAL_SCHEMA_VERSION = V2_SCHEMA
"""当前 emit 的 schema tag(PR-3 后固定为 v2)。"""

_LEGACY_SCHEMA_TAGS = frozenset({V1_SCHEMA, "lca.journal/1"})
"""读路径接受的 legacy schema tag 集合;不在这里的一律 fail-fast。"""


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
    """StampedEvent → v2 envelope record(ADR-0065 §三 / ADR-0101 PR-2)。

    新 emit 永远产 v2 envelope;``run_id`` 取 ``stamped.scope.run_id``;
    ``parent_event_id`` 由 engine.append 在 ledger 单临界区里填,这里透传。
    dataclass 字段本身已是事实字段(0065 §四 L1 / ADR-0101 PR-2),
    ``stamped_to_record`` 不再做 view-only 剥离;SSE 与 disk 一致,
    journal fact 即事实。

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
    # ADR-0096 MVA-1: EnvelopeV2Schema is the serialize source of truth
    # (schema_version / payload). On-disk jsonl, SSE, and replay still
    # consume the ADR-0065 JournalRecord dict (schema / data / committed_at).
    env = _DEFAULT_SCHEMA.serialize(record)
    return _envelope_v2_to_disk_record(env, record)


def _envelope_v2_to_disk_record(
    env: Mapping[str, Any],
    record: JournalRecord,
) -> dict[str, Any]:
    """Map EnvelopeV2 dict back to the ADR-0065 on-disk envelope.

    EnvelopeV2 uses ``schema_version`` / ``payload``; disk jsonl, SSE, and
    ``record_to_stamped`` still require ``schema: lca.journal/2`` / ``data``.
    Overlay EnvelopeV2 payload and identity fields onto ``JournalRecord.to_dict()``
    so ``serialize()`` is the source of those values without changing callers.
    """
    disk: dict[str, Any] = dict(record.to_dict())
    disk["event_id"] = env["event_id"]
    disk["run_id"] = env["run_id"]
    disk["run_seq"] = env["run_seq"]
    disk["occurred_at"] = env["occurred_at"]
    disk["plan_ref"] = env["plan_ref"]
    disk["data"] = env["payload"]
    raw_descriptor = disk.get("descriptor")
    descriptor: dict[str, Any] = dict(raw_descriptor) if isinstance(raw_descriptor, Mapping) else {}
    env_descriptor = env.get("descriptor") or {}
    if isinstance(env_descriptor, Mapping) and env_descriptor.get("type"):
        descriptor["type"] = env_descriptor["type"]
        disk["descriptor"] = descriptor
    return disk


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
    - ``arguments_ref`` / ``output_ref`` 在 disk v2 envelope 中以 dict 形式
      存储(jsonl),``record_to_stamped`` 重建为 ``EvidenceRef`` 实例
      (0065 §四 L5)。
    - 旧版 v2 envelope 可能仍带 ``state_ref`` / 6-key typed /
      ``*_preview`` / ``plugin_state``(ADR-0065 §四 旧 schema),``record_to_stamped``
      按 ``dataclasses.fields()`` 过滤未知键以保持前向兼容。
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
    # arguments_ref / output_ref dict → EvidenceRef (0065 §四 L5 typed field).
    for ref_key in ("arguments_ref", "output_ref"):
        if ref_key in data and isinstance(data[ref_key], dict):
            try:
                data[ref_key] = _EvidenceRef.from_dict(data[ref_key])
            except (ValueError, TypeError, KeyError):
                data[ref_key] = None
    # 按 dataclass 字段过滤未知键(旧 schema 的 code / command / language /
    # skill_id / skill_inputs / description / execution_env / arguments_preview /
    # result_preview / output_text / plugin_state / state_ref 等);output_truncated
    # 是 ToolInvoked 现存字段,不属于 legacy,正常保留。
    if dataclasses.is_dataclass(event_cls):
        allowed = {f.name for f in dataclasses.fields(event_cls)}
        data = {key: value for key, value in data.items() if key in allowed}
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
        plan_ref=str(normalized.get("plan_ref", "")),
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


_DISK_KEY_ORDER = (
    "schema",
    "run_seq",
    "descriptor",
    "_doc",
    "phase",
    "fact_id",
    "plugin",
    "data",
    "actor_role",
    "prev_event_type",
    "causation",
    "elapsed_ms",
    "occurred_at_iso",
    "occurred_at",
    "committed_at",
    "event_id",
    "run_id",
    "trace_id",
    "scope",
    "_redaction",
    "evidence",
    "plan_ref",
)
"""人眼可读顺序：type + payload + 中文 _doc 提前；身份 / 时间戳 / envelope 放后。"""


def _is_empty_default(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _omit_empty(value: Any) -> Any:
    """Drop null / empty-string / empty-collection defaults from nested dicts.

    Pure generator + comprehension — no scope ambiguity (see ADR-0122):
    the previous list-branch used ``[pruned for ...]`` where ``pruned`` was
    only ever assigned in the Mapping branch, causing ``UnboundLocalError``
    the moment any non-empty list was reached.
    """
    if isinstance(value, Mapping):
        pruned_items = ((str(k), _omit_empty(item)) for k, item in value.items())
        return {k: v for k, v in pruned_items if not _is_empty_default(v)}
    if isinstance(value, list):
        return [
            pruned
            for pruned in (_omit_empty(item) for item in value)
            if not _is_empty_default(pruned)
        ]
    return value


def _for_disk_reading(record: Mapping[str, Any]) -> dict[str, Any]:
    """Reorder envelope keys and omit empty defaults so the spine ledger is scannable.

    ``data`` / ``scope`` / ``causation`` 内的空默认值（None / "" / [] / {}）
    省略；envelope 字段按 ``_DISK_KEY_ORDER`` 排序，未列入的字段按原顺序
    追加在末尾，保证字段不丢。
    """
    prepared: dict[str, Any] = dict(record)
    data = prepared.get("data")
    if isinstance(data, Mapping):
        prepared["data"] = _omit_empty(data)
    scope = prepared.get("scope")
    if isinstance(scope, Mapping):
        prepared["scope"] = _omit_empty(scope)
    causation = prepared.get("causation")
    if isinstance(causation, Mapping):
        prepared["causation"] = _omit_empty(causation)
    ordered: dict[str, Any] = {}
    for key in _DISK_KEY_ORDER:
        if key in prepared:
            ordered[key] = prepared[key]
    for key, value in prepared.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def dumps_journal_record(record: Mapping[str, Any]) -> str:
    """把一条 journal envelope 格式化为缩进 JSON（stdlib ``json.dumps``）。

    每个事件一块、按结构换行；块与块之间再追加一个换行，便于 vim/jq 阅读。
    ``descriptor`` / ``_doc`` / ``data`` 提前，空 envelope 默认值省略。
    读路径用 ``JSONDecoder.raw_decode``，因此旧的单行 JSONL 仍然可解析。

    调用方应在 ``record`` 上先跑 enricher（见
    ``event_enrichers.EnrichmentPipeline``），由 enricher 决定哪些
    ``_doc`` / ``elapsed_ms`` / ``causation.parent_event_id`` 等可读性
    字段被注入；本函数只负责格式化。
    """
    return json.dumps(_for_disk_reading(record), ensure_ascii=False, indent=2) + "\n"


def iter_journal_records(
    text: str,
    *,
    source: str = "",
    strict: bool = True,
) -> Iterator[dict[str, Any]]:
    """解析 compact JSONL 或 indent=2 的 JSON 对象流。"""
    decoder = json.JSONDecoder()
    idx = 0
    length = len(text)
    while True:
        while idx < length and text[idx].isspace():
            idx += 1
        if idx >= length:
            return
        try:
            payload, end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError as err:
            if strict:
                loc = f"{source}:{err.lineno}" if source else f"offset {idx}"
                raise JournalFormatError(f"{loc} JSON 损坏:{err}") from err
            nxt = text.find("{", idx + 1)
            if nxt < 0:
                return
            idx = nxt
            continue
        if isinstance(payload, dict):
            yield payload
        elif strict:
            loc = source or "journal"
            raise JournalFormatError(f"{loc} 记录必须是 JSON object")
        idx = end


def load_journal_records(path: str | Path, *, strict: bool = True) -> list[dict[str, Any]]:
    """读取 journal 文件为 envelope dict 列表。"""
    file_path = Path(path)
    return list(
        iter_journal_records(
            file_path.read_text(encoding="utf-8"),
            source=str(file_path),
            strict=strict,
        )
    )


def read_journal(path: str | Path) -> list[StampedEvent]:
    """读取 jsonl journal 文件 → ``StampedEvent`` 流。

    两遍扫描:
    1. 先全部解析为 v2 envelope dict,收集 ``event_id → run_seq`` 映射。
    2. 再以映射为上下文构造 ``StampedEvent``,``parent_seq`` 精确解析。

    损坏 JSON 抛 ``JournalFormatError``;未知 ``descriptor.type`` 在
    第二遍返回 ``None`` 并跳过(前向兼容)。
    """
    file_path = Path(path)
    raw_records = load_journal_records(file_path)

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
    "dumps_journal_record",
    "iter_journal_records",
    "load_journal_records",
    "read_journal",
    "record_normalize",
    "record_to_journal_record",
    "record_to_stamped",
    "stamped_to_record",
]
