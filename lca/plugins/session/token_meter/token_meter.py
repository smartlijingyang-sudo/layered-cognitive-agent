"""启发式 TokenMeter —— 无 tokenizer 时的固定系数 fold（DSH token-meter 对位）。"""

from __future__ import annotations

import json
from typing import Any

from lca.contracts.observability.token_meter import TokenMeterNode, TokenMeterSnapshot
from lca.plugins.session.runtime.messages import derive_messages
from lca_kernel.events.fold import foldRequestHeader

__all__ = ["HeuristicTokenMeter", "estimate_text_tokens"]

_CHARS_PER_TOKEN = 4


def estimate_text_tokens(text: str) -> int:
    """固定启发式:ceil(len/4),无 tokenizer 时的 estimated 路径。"""
    if not text:
        return 0
    return max(1, (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("content") or block.get("text") or ""))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return json.dumps(message, default=str)


class HeuristicTokenMeter:
    """纯函数计量:derive_messages + header fold;usage 锚定需 header 一致。"""

    def measure(self, session: Any, *, header: dict[str, Any] | None = None) -> TokenMeterSnapshot:
        events = session.snapshot_events()
        messages = derive_messages(events)
        surface_tokens = sum(estimate_text_tokens(_message_text(m)) for m in messages)
        header_fold = foldRequestHeader(events)
        baseline = 0
        baseline_kind = "estimated"
        if header is not None and header_fold is not None:
            folded = {
                "config": dict(header_fold.config or {}),
                "system": header_fold.system,
                "tools": list(header_fold.tools or ()),
            }
            if folded == header:
                usage = _latest_usage(events)
                if usage is not None:
                    baseline = int(usage)
                    baseline_kind = "usage"
        log_revision = len(events)
        total = baseline + surface_tokens
        nodes = tuple(
            TokenMeterNode(seq=index, estimated_tokens=estimate_text_tokens(_message_text(m)))
            for index, m in enumerate(messages)
        )
        return TokenMeterSnapshot(
            log_revision=log_revision,
            baseline=baseline,
            surface_delta_tokens=surface_tokens,
            total_tokens=total,
            surface_tokens=surface_tokens,
            nodes=nodes,
            baseline_kind=baseline_kind,
        )


def _latest_usage(events: tuple[Any, ...]) -> int | None:
    for event in reversed(events):
        if getattr(event, "type", "") != "model.completed.v1":
            continue
        data = getattr(event, "data", {})
        if not isinstance(data, dict):
            continue
        usage = data.get("usage")
        if isinstance(usage, dict):
            total = usage.get("total_tokens") or usage.get("total")
            if isinstance(total, int):
                return total
    return None
