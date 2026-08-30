"""journal → SSE 帧序列化 —— 零翻译传输契约（ADR-0055 §十三 + ADR-0063 PR-7）。

``StampedEvent`` 经 ``stamped_to_record`` 落盘同构序列化，再包装为
标准 SSE 帧（``id`` = run_seq，``event`` = 事件类名，``data`` = JSON）。
``domain`` 字段从 ``EventDescriptorRegistry`` 查表附加，供前端着色分组。

ADR-0065 §四 + ADR-0101: live SSE frame 的 data 是 v2 envelope(同 disk),
``*_preview`` 字段已经在 ``stamped_to_record`` 阶段被剥离;SSE 是观察通道,
不再做任何脱敏或隐藏——journal fact 即事实。
"""

from __future__ import annotations

import json

from lca.contracts.models.observability.event import EventAudience
from lca.contracts.models.observability.journal import StampedEvent
from lca.layer0_infra.observability.event_catalog import descriptor_for
from lca.layer0_infra.observability.journal.journal_io import stamped_to_record

SSE_SENTINEL: None = None
"""队列/订阅关闭哨兵（与 ``LiveTail.close`` 对齐）。"""


def is_sse_visible(event_type: str) -> bool:
    """audience=restricted 的事件不进 SSE live 帧。"""
    descriptor = descriptor_for(event_type)
    return descriptor.audience is not EventAudience.RESTRICTED


def stamped_to_sse_frame(stamped: StampedEvent) -> str:
    """StampedEvent → SSE 文本帧（含 trailing blank line）。

    ADR-0101: SSE 是观察通道，journal fact 即事实，不做任何脱敏。
    data 已是 v2 envelope（无 preview / plugin_state 等 view-only 字段）。
    """
    event_type = type(stamped.event).__name__
    record = stamped_to_record(stamped)
    record["domain"] = descriptor_for(event_type).domain
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
