"""Record enrichers —— 落盘前对每条 journal record 做可读性 / 上下文增强。

设计原则(可插拔 + 可组合):
- 一个 ``RecordEnricher`` 就是一个纯函数:``record, ctx → record``;
  无副作用、不依赖运行时钟。
- ``EnrichmentContext`` 在整次 run 中保持不变,负责承载跨事件追踪
  (上一个 event_id / 上一个 occurred_at / 角色切换等)。
- 多个 enricher 按 ``priority`` 升序组合;priority 由调用方决定。
- 每个 enricher 是独立的可替换单元 —— 新增 enricher 不修改 projector。

调用路径:``FilesystemJournalStore.append`` → 拿 ``stamped`` →
``stamped_to_record`` → 走 ``EnrichmentPipeline.run`` → ``dumps_journal_record``
→ 落盘 + 可选 sidecar(``NarrativeSidecar``)。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class RecordEnricher(Protocol):
    """落盘前对 record dict 做增强的纯函数。

    实现要求:
    - ``name`` 是稳定标识,落盘 / 日志用。
    - ``enrich`` 不修改入参;返回新 dict。
    - 不得抛异常 —— 失败时降级(no-op + 内部 log)。
    """

    name: str

    def enrich(
        self,
        record: dict[str, Any],
        ctx: EnrichmentContext,
    ) -> dict[str, Any]: ...


@dataclass
class EnrichmentContext:
    """enricher 间共享的状态。"""

    run_id: str = ""
    trace_id: str = ""
    # scope_key → (last_event_id, last_occurred_at)
    last_seen: dict[tuple[str, str, str], tuple[str, float]] = field(default_factory=dict)
    # 当前 scope(actor_role, step, run_id) → 上一个 event_id;投影仪在 on_event 头部更新
    last_event_id: str = ""
    last_event_type: str = ""
    last_role: str = ""

    def scope_key(self, record: dict[str, Any]) -> tuple[str, str, str]:
        scope = record.get("scope") or {}
        return (
            str(scope.get("agent_role", "")),
            str(scope.get("step", "")),
            str(scope.get("run_id", "")),
        )

    def note_event(self, record: dict[str, Any]) -> None:
        """Projector 在 ``on_event`` 头部调用,登记刚刚发生的事件。"""
        event_id = str(record.get("event_id", ""))
        occurred = record.get("occurred_at")
        if not isinstance(occurred, (int, float)):
            return
        key = self.scope_key(record)
        self.last_seen[key] = (event_id, float(occurred))
        self.last_event_id = event_id
        self.last_event_type = str((record.get("descriptor") or {}).get("type", ""))
        self.last_role = key[0]


# ── 内置 enrichers ──────────────────────────────────────


class DocumentEnricher:
    """注入 ``_doc`` 字段(中文 summary / why / arch / layer)。"""

    name = "doc"

    def enrich(self, record: dict[str, Any], ctx: EnrichmentContext) -> dict[str, Any]:
        descriptor = record.get("descriptor") or {}
        event_type = str(descriptor.get("type", ""))
        if not event_type:
            return record
        try:
            from lca.infrastructure.observability.events.event_doc import doc_for
        except Exception:
            return record
        doc = doc_for(event_type)
        if doc is None:
            return record
        enriched = dict(record)
        enriched["_doc"] = {
            "summary": doc.summary,
            "why": doc.why,
            "arch": doc.arch,
            "layer": doc.layer,
        }
        return enriched


class TimestampEnricher:
    """注入 ``occurred_at_iso`` 与 ``elapsed_ms``(与同 scope 上一个事件的毫秒差)。"""

    name = "timestamp"

    def enrich(self, record: dict[str, Any], ctx: EnrichmentContext) -> dict[str, Any]:
        occurred = record.get("occurred_at")
        if not isinstance(occurred, (int, float)):
            return record
        enriched = dict(record)
        enriched["occurred_at_iso"] = _iso_utc(float(occurred))
        key = ctx.scope_key(record)
        last = ctx.last_seen.get(key)
        if last is not None:
            elapsed = max(0, int((float(occurred) - last[1]) * 1000))
            enriched["elapsed_ms"] = elapsed
        return enriched


class CausationEnricher:
    """注入 ``causation.parent_event_id`` 与 ``prev_event_type`` —— 修复 ADR-0065 §三

    的 known gap(``engine.py`` 不在公共 ``record()`` 路径串 parent_event_id)。
    投影仪层面维护同 scope 上一事件 ID,落盘时回填到 envelope。
    """

    name = "causation"

    def enrich(self, record: dict[str, Any], ctx: EnrichmentContext) -> dict[str, Any]:
        key = ctx.scope_key(record)
        last = ctx.last_seen.get(key)
        if not last or not last[0]:
            return record
        enriched = dict(record)
        causation = dict(enriched.get("causation") or {})
        if not causation.get("parent_event_id"):
            causation["parent_event_id"] = last[0]
            enriched["causation"] = causation
        enriched["prev_event_type"] = ctx.last_event_type
        return enriched


class PhaseLiftingEnricher:
    """把 ``RuntimeObserved.attributes`` 里的关键字段提到顶层,方便人眼检索。

    提升字段(仅当存在):
    - ``attributes.payload.semantic_phase`` → ``phase``
    - ``attributes.payload.fact_id`` → ``fact_id``
    - ``attributes.actor_role`` → ``actor_role``(若顶层 scope.agent_role 为空)
    - ``source`` → ``plugin``(语义前缀)
    """

    name = "phase_lift"

    def enrich(self, record: dict[str, Any], ctx: EnrichmentContext) -> dict[str, Any]:
        descriptor = record.get("descriptor") or {}
        if str(descriptor.get("type", "")) != "RuntimeObserved":
            return record
        data = record.get("data") or {}
        attributes = data.get("attributes") or {}
        if not isinstance(attributes, Mapping):
            return record
        payload = attributes.get("payload") or {}
        enriched = dict(record)
        if isinstance(payload, Mapping):
            phase = payload.get("semantic_phase")
            if isinstance(phase, str) and phase and "phase" not in enriched:
                enriched["phase"] = phase
            fact_id = payload.get("fact_id")
            if isinstance(fact_id, str) and fact_id and "fact_id" not in enriched:
                enriched["fact_id"] = fact_id
        plugin = data.get("source")
        if isinstance(plugin, str) and plugin and "plugin" not in enriched:
            enriched["plugin"] = plugin.split(".", 1)[0]
        actor = attributes.get("actor_role")
        if isinstance(actor, str) and actor and "actor_role" not in enriched:
            scope = enriched.get("scope") or {}
            if not scope.get("agent_role"):
                enriched["scope"] = {**scope, "agent_role": actor}
        return enriched


class RedactionMarkerEnricher:
    """记录 ``*_preview`` / ``output_text`` 字段的截断 / 长度状态。

    把标记写到顶层 ``_redaction`` 字段(而不是塞进 ``data``),保证
    ``data`` 字段保持 dataclass 可构造形状(replay 路径仍走
    ``event_cls(**data)``)。
    """

    name = "redaction_marker"

    _PREVIEW_KEYS = frozenset(
        {
            "prompt_preview",
            "response_preview",
            "rationale_preview",
            "objective_preview",
            "payload_preview",
            "subtask_preview",
            "arguments_preview",
            "result_preview",
            "content_preview",
        }
    )
    _TRUNCATE_HINT = 600  # 标准 verbosity 截断上限

    def enrich(self, record: dict[str, Any], ctx: EnrichmentContext) -> dict[str, Any]:
        data = record.get("data") or {}
        if not isinstance(data, Mapping):
            return record
        markers: dict[str, dict[str, int | bool]] = {}
        for key in self._PREVIEW_KEYS:
            if key not in data:
                continue
            value = data[key]
            if not isinstance(value, str):
                continue
            markers[key] = {
                "len": len(value),
                "truncated": len(value) >= self._TRUNCATE_HINT,
            }
        if "output_text" in data and isinstance(data["output_text"], str):
            markers["output_text"] = {"len": len(data["output_text"])}
        if not markers:
            return record
        enriched = dict(record)
        existing = enriched.get("_redaction")
        merged = dict(existing) if isinstance(existing, Mapping) else {}
        merged.update(markers)
        enriched["_redaction"] = merged
        return enriched


# ── 组合管线 ──────────────────────────────────────────


@dataclass
class EnrichmentPipeline:
    """按 ``name`` 去重、按声明顺序执行的 enricher 链。"""

    enrichers: tuple[RecordEnricher, ...] = ()
    context: EnrichmentContext = field(default_factory=EnrichmentContext)

    def run(self, record: Mapping[str, Any]) -> dict[str, Any]:
        current: dict[str, Any] = dict(record)
        for enricher in self.enrichers:
            try:
                current = enricher.enrich(current, self.context)
            except Exception:  # noqa: S112  enricher 失败降级为 no-op
                # enricher 失败不能影响落盘;保留之前的 current
                continue
        return current


def default_enrichers() -> tuple[RecordEnricher, ...]:
    """默认 enricher 组合 —— 与旧实现行为对齐 + 新增可读性字段。"""
    return (
        DocumentEnricher(),
        TimestampEnricher(),
        CausationEnricher(),
        PhaseLiftingEnricher(),
        RedactionMarkerEnricher(),
    )


def _iso_utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = [
    "CausationEnricher",
    "DocumentEnricher",
    "EnrichmentContext",
    "EnrichmentPipeline",
    "PhaseLiftingEnricher",
    "RecordEnricher",
    "RedactionMarkerEnricher",
    "TimestampEnricher",
    "default_enrichers",
]
