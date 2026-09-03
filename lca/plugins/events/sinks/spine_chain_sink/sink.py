"""spine_chain_sink plugin 实现（ADR-0181 试点）。

落盘时算 hash chain（causality_id + prev_event_hash）。试点仅 1 个 sink，
负责试点 EP 的落盘；其他 sink（file_sink / routing_file_sink / tracing_file_sink /
otel_trace）按 PR-7 迁移。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lca_kernel.events.mechanism import EventRef

log = logging.getLogger(__name__)


class SpineChainSink:
    """试点 sink plugin（FD-1 fail-fast 由机制保证：抛错即上抛）。"""

    _last_hash: str | None = None

    @classmethod
    def reset(cls) -> None:
        cls._last_hash = None

    def __init__(self, output_path: Path | None = None) -> None:
        default_path = Path(tempfile.gettempdir()) / "lca_spine_chain.jsonl"
        env_path = os.environ.get("LCA_SPINE_CHAIN_PATH")
        self.output_path = (
            Path(env_path) if env_path else (output_path or default_path)
        )

    def __call__(self, payload: Any, ref: EventRef) -> None:
        """sink callback（FD-1：抛错上抛 sender）。"""
        if not hasattr(payload, "execution_point"):
            # 非 SpineEventPayload 走 chain 失败，FD-1 上抛
            raise TypeError(
                f"SpineChainSink 只接 SpineEventPayload；got {type(payload).__name__}"
            )
        now = datetime.now(timezone.utc)
        ep = payload.execution_point
        record = {
            "event_id": ref.event_id,
            "category": ref.category,
            "execution_point": ep,
            "channel": payload.channel,
            "payload": payload.payload,
            "ts": now.isoformat(),
        }
        # 算 hash chain
        causality_payload = json.dumps(
            {
                "execution_point": ep,
                "channel": payload.channel,
                "payload": payload.payload,
                "event_id": ref.event_id,
            },
            sort_keys=True,
            default=str,
        )
        causality_id = "sha256:" + hashlib.sha256(causality_payload.encode()).hexdigest()
        new_hash = (
            "sha256:"
            + hashlib.sha256(((self._last_hash or "") + causality_id).encode("utf-8")).hexdigest()
        )
        record["causality_id"] = causality_id
        record["prev_event_hash"] = self._last_hash
        record["event_hash"] = new_hash
        SpineChainSink._last_hash = new_hash

        # 落盘（FD-1：IO 错误上抛 sender）
        with self.output_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


__all__ = ["SpineChainSink"]
