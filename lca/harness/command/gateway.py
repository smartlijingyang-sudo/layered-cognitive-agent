"""Compatibility shim — do not use. Renamed to :mod:`lca.harness.command.dispatcher`.

ADR-0119 followup-2 (2026-08-31): 原模块路径 ``lca.harness.command.gateway``
改名为 ``lca.harness.command.dispatcher``。本 shim 模块保留 1 release 兼容期,
过期日 2026-12-31,届时本文件会被删除。
"""

from __future__ import annotations

from lca.harness.command.dispatcher import SessionCommandCarrier

__all__ = ["SessionCommandCarrier"]
