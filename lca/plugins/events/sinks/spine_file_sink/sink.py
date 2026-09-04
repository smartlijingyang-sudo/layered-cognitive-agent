"""spine_file_sink plugin 实现（ADR-0181 PR-8 shim / ADR-0183 PR-7；record 入口 ADR-0183 PR-5）。

# COMPAT(delete-when: PR-9, tracking: ADR-0181)
# shim：<run_dir>/<run_id>.spine.jsonl 落盘入口。record 构造 =
# build_record() 单一入口（ADR-0183 §3.5）；落盘 = SpineSink（I-FW-SSOT-1
# 唯一 writer）；字节布局 = SpineEventRecord.to_dict() 10 键含 trace_id
# （sort_keys）。

PR-9 旧 spine 全退役时一并删除本 shim（rg FileSink lca/infrastructure/
= 0 触发）。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from lca_kernel.events.bus import EventRef
from lca_kernel.events.sinks.spine_sink import SpineSink
from lca_kernel.events.spine_runtime import build_record, is_spine_event

if TYPE_CHECKING:
    from lca_kernel.events.spine_runtime import SpineEventRecord


def _run_id_of(event_id: str) -> str:
    """从 ``event_id`` 推导 run_id；Session 投递契约形态 ``"{session.id}:{seq}"``。

    投递两侧把 ``session.id`` 写成 event_id 前缀
    （``bus_facade._event_ref`` / ``event_session._event_ref_from_session``），
    本函数按该形态反解（``rpartition`` 容忍 run id 自带冒号）。
    无 run 上下文（无冒号 / 空前缀 / seq 非数字）抛 ``ValueError`` ——
    不落任何默认文件；Session 投递边界负责 contained + 结构化日志。
    """
    run_id, sep, seq = event_id.rpartition(":")
    if not sep or not run_id or not seq.isdigit():
        raise ValueError(
            f"SpineFileSink 无法从 event_id={event_id!r} 推导 run_id"
            "（Session 投递契约 '{session.id}:{seq}'）；无 run 上下文，不落盘"
        )
    return run_id


class SpineFileSink:
    """Session.observe / SinkBackend 落盘入口；委托 SpineSink SSOT per-run 落盘。

    生产 boot 经 Session.observe catalog 登记(ADR-0186 PR-3f；见同目录
    manifest)。run_id 逐事件从 ``ref.event_id`` / ``record.event_id`` 推导
    （:func:`_run_id_of`），每条事件经独立 SpineSink 打开/落盘/关闭：
    shim 不持有 run 生命周期，fd 不跨 run 滞留，也无默认 run 兜底。
    每条事件经 ``build_record()`` 构造 ``SpineEventRecord`` 后交
    ``SpineSink.append``。字节布局 = ``SpineEventRecord.to_dict()`` 10 键
    （含 ``trace_id``；ADR-0183 §3.5 SSOT，plugin 不可改）。

    失败语义：无 run 上下文 → 上抛（投递侧 contained + 记
    ``session.observer.failed``，不杀 run）；sink path 失败上抛；
    无静默枚举 fallback。

    实现 :class:`lca_kernel.events.sinks.SinkBackend` Protocol：除老
    ``__call__`` 兼容层外,提供 :meth:`append` / :meth:`flush` / :meth:`close`。
    ``EventBus.mount_sink`` API 仍可用,但生产路径不经 mount_sink。
    """

    def __init__(self, run_dir: Path | None = None) -> None:
        # 落点契约(模块 docstring / ADR-0165.1 layout)= per-run 目录
        # ``traces/runs/<run_id>/<run_id>.spine.jsonl``,与 spine.sink.file
        # 的 run 布局一致;run_dir 缺省曾退回 ``Path.cwd()`` 造成仓库根
        # 散落游离镜像文件,已收口。
        base = run_dir if run_dir is not None else Path("traces") / "runs" / "{run_id}"
        self._path_template = str(base / "{run_id}.spine.jsonl")
        self._closed = False

    def __call__(self, payload: Any, ref: EventRef) -> None:
        # COMPAT(跟踪:ADR-0181 PR-8 shim / ADR-0184 PR-1;老 EventBus.subscribe
        # callback 与 mount_sink→_dispatch_sinks→backend.append 仍可用。
        # 生产 boot 走 Session.observe catalog,不经 mount_sink)。
        # delete-when:EventBus.subscribe(零 sinks 路径)全部收口。
        if not is_spine_event(payload):
            raise TypeError(f"SpineFileSink 只接 SpineEventPayload；got {type(payload).__name__}")
        self._append(build_record(payload, ref), ref.event_id)

    def append(self, record: SpineEventRecord) -> None:
        """SinkBackend Protocol 实现(ADR-0184 PR-2):接收已构造好的 record 直接落盘。

        run_id 同样从 ``record.event_id`` 推导（与 ``__call__`` 同源契约），
        本方法不重复序列化。
        """
        self._append(record, record.event_id)

    def flush(self) -> None:
        """无常驻缓冲：每次 append 随 SpineSink close 已完成 flush + fsync。"""
        if self._closed:
            raise RuntimeError("SpineFileSink 已关闭，不可 flush")

    def close(self) -> None:
        """标记关闭，后续 append / flush 上抛；无跨事件句柄可释放。"""
        self._closed = True

    def _append(self, record: SpineEventRecord, event_id: str) -> None:
        if self._closed:
            raise RuntimeError("SpineFileSink 已关闭，不可 append")
        run_id = _run_id_of(event_id)
        target = Path(self._path_template.replace("{run_id}", run_id))
        target.parent.mkdir(parents=True, exist_ok=True)
        inner = SpineSink(path_template=self._path_template)
        inner.set_run_id(run_id)
        try:
            inner.append(record)
        finally:
            inner.close()


__all__ = ["SpineFileSink"]
