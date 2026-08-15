"""journal → SSE 帧序列化 —— 零翻译传输契约（ADR-0055 §十三）。

``StampedEvent`` 经 ``stamped_to_record`` 落盘同构序列化，再包装为
标准 SSE 帧（``id`` = seq，``event`` = 事件类名，``data`` = JSON）。
``domain`` 字段从 ``JOURNAL_CATALOG`` 查表附加，供前端着色分组。

audience 分类驱动 SSE 过滤：``audience=restricted`` 的事件（如 ReasoningDelta）
默认不进 SSE live 帧；``audience=end_user`` 的事件才推送。
"""

from __future__ import annotations

import json

from lca.contracts.models.observability.journal import StampedEvent
from lca.contracts.models.observability.journal_catalog import (
    JOURNAL_CATALOG,
    JOURNAL_CATALOG_META,
)
from lca.layer0_infra.observability.journal.journal_io import stamped_to_record

# Lossy journal strings — jsonl/OTel only. Live UI uses plugin_state / files.
_LIVE_REDACT_KEYS = frozenset({"result_preview", "arguments_preview"})

SSE_SENTINEL: None = None
"""队列/订阅关闭哨兵（与 ``SSEJournalProjector.close`` 对齐）。"""


def is_sse_visible(event_type: str) -> bool:
    """audience=restricted 的事件不进 SSE live 帧。"""
    meta = JOURNAL_CATALOG_META.get(event_type)
    if meta is None:
        return True  # 未分类事件默认可见（向前兼容）
    return meta.audience != "restricted"


def stamped_to_sse_frame(stamped: StampedEvent, *, redact: bool = True) -> str:
    """StampedEvent → SSE 文本帧（含 trailing blank line）。

    ``redact=True``（LobeHub live）：抹掉 preview 字符串。
    ``redact=False``（ops journal）：保留预览，给终端 debug。
    """
    event_type = type(stamped.event).__name__
    record = stamped_to_record(stamped)
    catalog = JOURNAL_CATALOG.get(event_type)
    if catalog is not None:
        record["domain"] = catalog.domain.value
    event = record.get("event")
    if redact and isinstance(event, dict):
        for key in _LIVE_REDACT_KEYS:
            if key in event:
                event[key] = ""
    payload = json.dumps(record, ensure_ascii=False, default=str)
    return f"id: {stamped.seq}\nevent: {event_type}\ndata: {payload}\n\n"


def parse_last_event_id(header_value: str | None) -> int:
    """解析 ``Last-Event-ID`` 请求头；缺省或非法 → 0（从头回放）。"""
    if not header_value:
        return 0
    try:
        return max(0, int(header_value.strip()))
    except ValueError:
        return 0


def frames_after_seq(frames: list[str], after_seq: int) -> list[str]:
    """从已缓冲 SSE 帧列表中筛出 seq > after_seq 的帧。"""
    if after_seq <= 0:
        return list(frames)
    out: list[str] = []
    for frame in frames:
        seq = _seq_from_frame(frame)
        if seq is not None and seq > after_seq:
            out.append(frame)
    return out


def _seq_from_frame(frame: str) -> int | None:
    for line in frame.splitlines():
        if line.startswith("id: "):
            try:
                return int(line[4:].strip())
            except ValueError:
                return None
    return None
