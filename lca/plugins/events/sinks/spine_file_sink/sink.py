"""spine_file_sink plugin 实现（ADR-0181 PR-8 shim / ADR-0183 PR-7；record 入口 ADR-0183 PR-5）。

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

from lca_kernel.events.bus import EventRef
from lca_kernel.events.sinks.spine_sink import SpineSink
from lca_kernel.events.spine_runtime import build_record, is_spine_event

log = logging.getLogger(__name__)


class SpineFileSink:
    """EventBus callback 入口；落盘委托 SpineSink SSOT 路径。

    manifest 订阅全部 spine EP category；每条事件经 ``build_record()`` 构造
    ``SpineEventRecord`` 后交 ``SpineSink.append``。字节布局 =
    ``SpineEventRecord.to_dict()`` 9 键（ADR-0183 §3.5 SSOT，plugin 不可改）。

    失败语义：sink path 失败上抛；订阅路径由机制 FD-1 fail-fast 显式记日志，
    无静默枚举 fallback。

    实现 :class:`lca_kernel.events.sinks.SinkBackend` Protocol(PR-2 起):除老
    ``__call__`` 兼容层外,新增 :meth:`append` / :meth:`flush` / :meth:`close`
    三件套,允许 ``EventBus.mount_sink`` 直接装载。sink 写入仍走底层
    :class:`lca_kernel.events.sinks.spine_sink.SpineSink` SSOT。
    """

    def __init__(self, run_dir: Path | None = None) -> None:
        # run_id 哨兵：shim 不感知 run 生命周期；PR-9 并入
        # lca_kernel/events/sinks/spine_file_sink.py 后由 set_run_id 注入。
        target = run_dir or Path.cwd()
        self._inner = SpineSink(path_template=str(target / "{run_id}.spine.jsonl"))
        self._inner.set_run_id("default-run")

    def __call__(self, payload: Any, ref: EventRef) -> None:
        # COMPAT(跟踪:ADR-0181 PR-8 shim / ADR-0184 PR-1;老 EventBus.subscribe
        # callback 路径仍可用,新路径走 mount_sink 后由 _dispatch_sinks →
        # backend.append(record) 接管)。delete-when:EventBus.subscribe(零 sinks
        # 路径)全部收口。
        if not is_spine_event(payload):
            raise TypeError(f"SpineFileSink 只接 SpineEventPayload；got {type(payload).__name__}")
        self._inner.append(build_record(payload, ref))

    def append(self, record) -> None:
        """SinkBackend Protocol 实现(ADR-0184 PR-2):接收已构造好的 record 直接落盘。

        ``record`` 通常由 :meth:`lca_kernel.events.bus.EventBus._dispatch_sinks`
        内部经 :func:`lca_kernel.events.spine_runtime.build_record` 构造,
        本方法不重复序列化。
        """
        self._inner.append(record)

    def flush(self) -> None:
        self._inner.flush()

    def close(self) -> None:
        self._inner.close()


__all__ = ["SpineFileSink"]
