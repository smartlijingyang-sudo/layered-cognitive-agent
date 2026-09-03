"""spine_chain_sink plugin 实现（ADR-0181 PR-2 复审）。

用 :mod:`lca_kernel.events.spine_runtime` 提取的 helpers：序列化 / chain
计算 / 时钟 / 落盘路径一律走 helpers，本 plugin 只负责"落盘"一件事。

PR-2 删-when：见 lca_kernel/events/spine_runtime.py 顶部说明。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from lca_kernel.events import EventRef
from lca_kernel.events.spine_runtime import (
    SpineChainContext,
    build_record,
    default_chain_path,
    is_spine_event,
)

log = logging.getLogger(__name__)


class SpineChainSink:
    """spine chain 落盘 sink（FD-1 fail-fast 由机制保证：抛错即上抛）。

    PR-2 复审：原 82 行实现收敛为 30 行（核心 = build record + append jsonl），
    chain / 时钟 / 路径 / 序列化全部走 spine_runtime helpers。
    """

    def __init__(self, output_path: Path | None = None) -> None:
        self.output_path = output_path or default_chain_path()
        self._chain = SpineChainContext()

    def __call__(self, payload: Any, ref: EventRef) -> None:
        """sink callback（FD-1：抛错上抛 sender）。"""
        if not is_spine_event(payload):
            raise TypeError(f"SpineChainSink 只接 SpineEventPayload；got {type(payload).__name__}")
        # build_record = record 构造单一入口（ADR-0183 §3.5 PR-5）；
        # chain 显式传入时 prev_event_hash 取 chain.prev_hash，落盘字节不变。
        record = build_record(payload, ref, chain=self._chain)
        with self.output_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        if record.event_hash is not None:
            self._chain = SpineChainContext(prev_hash=record.event_hash)


__all__ = ["SpineChainSink"]
