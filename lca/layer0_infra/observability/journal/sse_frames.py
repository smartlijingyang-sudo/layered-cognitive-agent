"""journal → SSE 帧序列化 —— 零翻译传输契约（ADR-0055 §十三 + ADR-0063 PR-7）。

``StampedEvent`` 经 ``stamped_to_record`` 落盘同构序列化，再包装为
标准 SSE 帧（``id`` = run_seq，``event`` = 事件类名，``data`` = JSON）。
``domain`` 字段从 ``EventDescriptorRegistry`` 查表附加，供前端着色分组。

ADR-0065 §四: live SSE frame 的 data 是 v2 envelope(同 disk),
``*_preview`` 字段已经在 ``stamped_to_record`` 阶段被剥离 —— 不再需要
"redact 改 "" " 这种负向脱敏(0064 老路);redact 选项保留供 ops mode
调试,但 live 模式默认 redact=True 与 disk 一致。
"""

from __future__ import annotations

import json

from lca.contracts.models.observability.event import EventAudience
from lca.contracts.models.observability.journal import StampedEvent
from lca.layer0_infra.observability.event_catalog import descriptor_for
from lca.layer0_infra.observability.journal.journal_io import stamped_to_record

# Live UI guard: 虽已从 disk data 剥离 preview,旧 client 仍可能用 v1 字段
# 探测并报警;redact 兼容 fallback 以支持 ops debug。
_LIVE_REDACT_KEYS = frozenset({"result_preview", "arguments_preview"})

SSE_SENTINEL: None = None
"""队列/订阅关闭哨兵（与 ``LiveTail.close`` 对齐）。"""


def is_sse_visible(event_type: str) -> bool:
    """audience=restricted 的事件不进 SSE live 帧。"""
    descriptor = descriptor_for(event_type)
    return descriptor.audience is not EventAudience.RESTRICTED


def stamped_to_sse_frame(stamped: StampedEvent, *, redact: bool = True) -> str:
    """StampedEvent → SSE 文本帧（含 trailing blank line）。

    ``redact=True``(LobeHub live 默认):data 已是 v2 envelope(无 preview /
    plugin_state);参数保留供 ops debug 模式。

    ``redact=False``(ops journal):legacy v1 字段探测并按 ``_LIVE_REDACT_KEYS``
    置空,保证旧 client 不会读到 leak。
    """
    event_type = type(stamped.event).__name__
    record = stamped_to_record(stamped)
    record["domain"] = descriptor_for(event_type).domain
    if not redact:
        data_section = record.get("data")
        if isinstance(data_section, dict):
            for key in _LIVE_REDACT_KEYS:
                if key in data_section:
                    data_section[key] = ""
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
