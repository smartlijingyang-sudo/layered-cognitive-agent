"""spine_file_sink plugin 实现（ADR-0181 PR-8 shim；record 入口 ADR-0183 PR-5）。

# COMPAT(delete-when: PR-9, tracking: ADR-0181)
# shim：<run_dir>/default-run.spine.jsonl 落盘入口。record 构造 =
# build_record() 单一入口（ADR-0183 §3.5）；落盘 = SpineSink（I-FW-SSOT-1
# 唯一 writer）；字节布局 = SpineEventRecord.to_dict() 9 键（sort_keys）。

PR-9 旧 spine 全退役时一并删除本 shim（rg FileSink lca/infrastructure/
= 0 触发）。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from lca_kernel.events.mechanism import EventRef
from lca_kernel.events.sinks.spine_sink import SpineSink
from lca_kernel.events.spine_runtime import build_record, is_spine_event

log = logging.getLogger(__name__)


class SpineFileSink:
    """EventMechanism callback 入口；落盘委托 SpineSink SSOT 路径。

    manifest 订阅全部 spine EP category；每条事件经 ``build_record()`` 构造
    ``SpineEventRecord`` 后交 ``SpineSink.append``。字节布局 =
    ``SpineEventRecord.to_dict()`` 9 键（ADR-0183 §3.5 SSOT，plugin 不可改）。

    失败语义：callback 异常上抛；订阅路径由机制 FD-2 contained 显式记日志，
    无静默枚举 fallback。
    """

    def __init__(self, run_dir: Path | None = None) -> None:
        # run_id 哨兵：shim 不感知 run 生命周期；PR-9 并入
        # lca_kernel/events/sinks/spine_file_sink.py 后由 set_run_id 注入。
        target = run_dir or Path.cwd()
        self._inner = SpineSink(path_template=str(target / "{run_id}.spine.jsonl"))
        self._inner.set_run_id("default-run")

    def __call__(self, payload: Any, ref: EventRef) -> None:
        if not is_spine_event(payload):
            raise TypeError(f"SpineFileSink 只接 SpineEventPayload；got {type(payload).__name__}")
        self._inner.append(build_record(payload, ref))

    def flush(self) -> None:
        self._inner.flush()

    def close(self) -> None:
        self._inner.close()


__all__ = ["SpineFileSink"]
