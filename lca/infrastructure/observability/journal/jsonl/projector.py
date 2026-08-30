"""JsonlJournalProjector —— journal 落盘投影（ADR-0037 record-as-data）。

每次 ``on_event`` 把 ``StampedEvent`` 落成一块 indent=2 JSON；jq /
``JSONDecoder.raw_decode`` 可查、replay 可重建。落盘的是叙事真相
（journal），不是 span 形状。

流式增量（``StepTextDelta`` / ``ReasoningDelta`` / ``SandboxOutputDelta``）
按 (类型, step/invocation, channel/stream) 在落盘前拼成一次完整文本，
避免 token 级 envelope 淹没 journal.jsonl。LiveTail / SSE 仍接收原始增量。

合并语义：合并记录的 ``run_seq`` = 组内第一条事件的 seq（first-of-group）。
组内后续事件的 seq 被吸收进 ``text_delta``，不再单独落盘；LiveTail /
SSE 仍按原 seq 推送。``journal.jsonl`` 的最后一条 ``run_seq`` 仍等于
RunStore 提交的最后 seq，doctor 的 ``jsonl_seq_eq_tail_seq`` 通过；
中间 seq 跳号只代表被合并的 delta，不破坏 replay / 物化重建。

可插拔增强（``event_enrichers.py``）:
- 默认装入 ``DocumentEnricher`` / ``TimestampEnricher`` /
  ``CausationEnricher`` / ``PhaseLiftingEnricher`` /
  ``RedactionMarkerEnricher``。
- ``CausationEnricher`` 在投影仪层面回填 ``causation.parent_event_id``，
  补齐 engine 公共 record() 路径的 known gap。

可插拔 sidecar:
- ``NarrativeSidecar`` 同步写 ``journal.<name>.narrative.md``；
  ``SidecarHook`` Protocol 让其它投影（snapshot / metrics）易接入。
"""

from __future__ import annotations

import contextlib
import dataclasses
from collections.abc import Hashable
from pathlib import Path
from typing import TextIO

from lca.contracts.models.observability.journal import (
    ReasoningDelta,
    SandboxOutputDelta,
    StampedEvent,
    StepTextDelta,
)
from lca.contracts.protocols import JournalProjector
from lca.infrastructure.observability.journal.engine.journal_io import (
    dumps_journal_record,
    stamped_to_record,
)
from lca.infrastructure.observability.journal.enrichment.event_enrichers import (
    EnrichmentContext,
    EnrichmentPipeline,
    RecordEnricher,
    default_enrichers,
)
from lca.infrastructure.observability.journal.stream.narrative_sidecar import (
    NarrativeSidecar,
    SidecarHook,
)

_DeltaKey = tuple[Hashable, ...]


# Fields that live on the ToolInvoked event but are SSE-only — jsonl stays
# pure fact.  See ADR-XXXX (renderer-facing projection).
_SSE_ONLY_FIELDS: frozenset[str] = frozenset({"projected_state"})


def _strip_sse_only_fields(record: dict) -> None:
    """Remove SSE-only fields from a record's payload before disk write.

    Mutates ``record["data"]`` in place.  No-op when the record has no data
    dict or the field is absent.
    """
    data = record.get("data")
    if not isinstance(data, dict):
        return
    for field in _SSE_ONLY_FIELDS:
        data.pop(field, None)


def _delta_key(stamped: StampedEvent) -> _DeltaKey | None:
    """Return a coalescing key for stream-delta events, else None."""
    event = stamped.event
    if isinstance(event, StepTextDelta):
        return ("StepTextDelta", event.step, event.channel)
    if isinstance(event, ReasoningDelta):
        return ("ReasoningDelta", event.step)
    if isinstance(event, SandboxOutputDelta):
        return ("SandboxOutputDelta", event.invocation_id, event.stream)
    return None


def _text_delta_of(stamped: StampedEvent) -> str:
    event = stamped.event
    if isinstance(event, (StepTextDelta, ReasoningDelta, SandboxOutputDelta)):
        return event.text_delta
    raw = stamped.data.get("text_delta", "")
    return raw if isinstance(raw, str) else ""


def _fragment_seq(stamped: StampedEvent) -> int:
    event = stamped.event
    seq = getattr(event, "seq", stamped.data.get("seq", 0))
    return int(seq) if isinstance(seq, int) else 0


def _coalesce_deltas(events: list[StampedEvent]) -> StampedEvent:
    """Merge a same-key delta run into one stamped event with concatenated text.

    ``run_seq`` / ``event_id`` come from the FIRST event in the group so the
    on-disk seq stays monotonic and the last record's ``run_seq`` equals the
    last seq committed by RunStore (doctor ``jsonl_seq_eq_tail_seq``）。
    """
    first = events[0]
    combined = "".join(_text_delta_of(item) for item in events)
    first_seq = _fragment_seq(first)
    event = first.event
    if isinstance(event, (StepTextDelta, ReasoningDelta, SandboxOutputDelta)):
        event = dataclasses.replace(event, text_delta=combined, seq=first_seq)
        data = dataclasses.asdict(event)
    else:
        data = dict(first.data)
        data["text_delta"] = combined
        data["seq"] = first_seq
    return dataclasses.replace(first, event=event, data=data)


class JsonlJournalProjector(JournalProjector):
    """journal 事件按 JSON 结构缩进追加写入文件；可挂 enricher 与 sidecar。"""

    def __init__(
        self,
        output_path: str | Path = "traces/lca_journal.jsonl",
        *,
        enrichers: tuple[RecordEnricher, ...] | None = None,
        sidecars: tuple[SidecarHook, ...] = (),
        run_id: str = "",
        trace_id: str = "",
    ) -> None:
        self._path = Path(output_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh: TextIO = self._path.open("a", encoding="utf-8")
        self._delta_buffers: dict[_DeltaKey, list[StampedEvent]] = {}
        self._context = EnrichmentContext(run_id=run_id, trace_id=trace_id)
        self._pipeline = EnrichmentPipeline(
            enrichers=enrichers if enrichers is not None else default_enrichers(),
            context=self._context,
        )
        self._sidecars: tuple[SidecarHook, ...] = sidecars
        # 若未指定 sidecar，默认挂 NarrativeSidecar 在 jsonl 旁边
        self._owns_sidecar = False
        if not sidecars:
            md = self._path.with_name(self._path.name + ".narrative.md")
            self._sidecars = (NarrativeSidecar(md),)
            self._owns_sidecar = True

    def on_event(self, stamped: StampedEvent) -> None:
        key = _delta_key(stamped)
        if key is not None:
            self._delta_buffers.setdefault(key, []).append(stamped)
            return
        self._flush_delta_buffers()
        self._write(stamped)

    def flush(self) -> None:
        self._flush_delta_buffers()
        self._fh.flush()

    def close(self) -> None:
        try:
            self.flush()
        finally:
            try:
                self._fh.close()
            finally:
                if self._owns_sidecar:
                    for sc in self._sidecars:
                        # sidecar 是 best-effort；失败不能阻塞主流程收尾
                        with contextlib.suppress(Exception):
                            sc.finalize()

    def _flush_delta_buffers(self) -> None:
        if not self._delta_buffers:
            return
        pending = list(self._delta_buffers.values())
        self._delta_buffers.clear()
        for group in pending:
            if group:
                self._write(_coalesce_deltas(group))

    def _write(self, stamped: StampedEvent) -> None:
        record = stamped_to_record(stamped)
        # ADR-XXXX: projected_state is SSE-only; jsonl stays pure fact.
        _strip_sse_only_fields(record)
        enriched = self._pipeline.run(record)
        # 让 enricher 看到刚发生的事件，以便计算 elapsed_ms / parent_event_id
        self._context.note_event(enriched)
        self._fh.write(dumps_journal_record(enriched))
        self._fh.flush()  # trace 文件逐条持久：进程崩溃不丢已记录事件
        for sidecar in self._sidecars:
            try:
                sidecar.on_event(stamped, enriched)
            except Exception:  # noqa: S112  best-effort guard
                # sidecar 失败不能影响主 ledger 落盘
                continue
