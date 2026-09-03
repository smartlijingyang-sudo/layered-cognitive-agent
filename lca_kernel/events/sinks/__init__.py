"""Sink 后端协议 + 默认实现 —— ADR-0183 §3.4。

SpineSink 是事实链 SSOT 默认实现。
plugin 可实现其它后端(KAFKA / S3 / 自研),但必须实现同一接口。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from lca_kernel.events.spine_runtime import SpineEventRecord


class SinkBackend(Protocol):
    """落盘后端协议。

    SpineSink 是默认实现（事实链 SSOT）。
    plugin 可实现其它后端（KAFKA / S3 / 自研），但必须实现同一接口。
    """

    def append(self, record: SpineEventRecord) -> None:
        """落盘一条 record。

        字节布局由调用方通过 ``record.to_dict()`` 统一保证（SSOT），backend
        不可改字段名 / 字段顺序 / 序列化选项。
        """
        ...

    def flush(self) -> None:
        """强制 flush 到 durable 介质（fsync）。

        sink 内部 batch fsync 策略时，本方法必须立即触发一次 fsync。
        """
        ...

    def close(self) -> None:
        """flush + 关闭底层句柄。

        调用后再调 append/flush 应 raise（具体异常类由各 backend 定义）。
        """
        ...


__all__ = ["SinkBackend"]
