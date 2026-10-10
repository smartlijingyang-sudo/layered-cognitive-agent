"""event identity via ULID —— ADR-0097 + ADR-0096 MVA-2.

实现已下沉 ``lca.contracts.observability.event.stable_ulid_identity``；
本模块为兼容 re-export（既有测试与 seam 文档引用此路径）。
"""

from __future__ import annotations

from lca.contracts.observability.event.stable_ulid_identity import (
    StableUlidIdentity as StableUlidIdentity,
)

__all__ = ["StableUlidIdentity"]
