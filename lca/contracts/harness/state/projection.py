"""Session projection 契约（spec §2.2.6）。

投影注册表/单元契约归 ``lca/contracts/protocols/session/projection_unit.py``
（ADR-0186 后的 DSH 对齐形态）；本模块保留跨平面共享的快照类型。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ProjectionSnapshot:
    """一个 session 上全部客户端可见单元的一次一致读切。

    ``as_of_seq`` 是共享水位 —— 所有值反映的最后一条事件的 seq
    （空日志为 ``-1``）；``values`` 是 key → 完整当前值。客户端收
    完整值，不收 fold 中间态；调用方不得改动返回结构。
    """

    as_of_seq: int
    values: Mapping[str, Any]


__all__ = ["ProjectionSnapshot"]
