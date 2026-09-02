"""Spine WritePort — cursor 唯一允许调用的 spine 面(ADR-0169 D1 / L10)。

仅 append 语义写入;spine 内部负责 seq 分配与 sink flush。
cursor 不得直接 import EventSpine / Serializer / Storage(ADR-0169 L4 I-PLUG1)。
"""

from __future__ import annotations

from typing import Any, Protocol


class WritePort(Protocol):
    """append-only 语义写入;返回分配的 seq。"""

    def append(
        self,
        *,
        execution_point: str,
        payload: dict[str, Any],
        run_id: str,
        seq: int,
        incarnation: int,
        phase: str | None,
    ) -> int: ...


__all__ = ["WritePort"]
