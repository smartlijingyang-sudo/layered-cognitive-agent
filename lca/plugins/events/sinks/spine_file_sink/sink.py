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
    """Session.observe / SinkBackend 落盘入口；委托 SpineSink SSOT 路径。

    生产 boot 经 Session.observe catalog 登记(ADR-0186 PR-3f；见同目录
    manifest)。每条事件经 ``build_record()`` 构造 ``SpineEventRecord`` 后交
    ``SpineSink.append``。字节布局 = ``SpineEventRecord.to_dict()`` 9 键
    （ADR-0183 §3.5 SSOT，plugin 不可改）。

    失败语义：sink path 失败上抛；无静默枚举 fallback。

    实现 :class:`lca_kernel.events.sinks.SinkBackend` Protocol：除老
    ``__call__`` 兼容层外,提供 :meth:`append` / :meth:`flush` / :meth:`close`。
    ``EventBus.mount_sink`` API 仍可用,但生产路径不经 mount_sink。
    """

    def __init__(self, run_dir: Path | None = None) -> None:
        # run_id 哨兵：shim 不感知 run 生命周期；PR-9 并入
        # lca_kernel/events/sinks/spine_file_sink.py 后由 set_run_id 注入。
        target = run_dir or Path.cwd()
        self._inner = SpineSink(path_template=str(target / "{run_id}.spine.jsonl"))
        self._inner.set_run_id("default-run")

    def __call__(self, payload: Any, ref: EventRef) -> None:
        # COMPAT(跟踪:ADR-0181 PR-8 shim / ADR-0184 PR-1;老 EventBus.subscribe
        # callback 与 mount_sink→_dispatch_sinks→backend.append 仍可用。
        # 生产 boot 走 Session.observe catalog,不经 mount_sink)。
        # delete-when:EventBus.subscribe(零 sinks 路径)全部收口。
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
