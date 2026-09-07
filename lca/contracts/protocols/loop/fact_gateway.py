"""FactGateway loop 机制层契约(ADR-0194 §3.1)。

Loop 层唯一事实生产门面:cognition 不得 import,全部 durable 事实经
``Session.append``。契约层只描述类型与协议,不含行为/IO(ADR-0015)。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, TypeAlias, runtime_checkable

# @session_event 注册的 catalog payload 实例(见 ``lca.contracts.harness``)。
SessionCatalogEvent: TypeAlias = Any
# ``SPINE_EXECUTION_POINTS`` / ``EXECUTION_POINTS`` 白名单成员。
SpineExecutionPoint: TypeAlias = str
# 诊断面事实;``append_diagnostic`` 允许 no-op 不落盘。
DiagnosticFact: TypeAlias = Any


@dataclass(frozen=True, slots=True)
class AppendReceipt:
    """``Session.append`` 回执的最小投影。"""

    event_type: str
    seq: int
    session_id: str
    time: int


@runtime_checkable
class FactGateway(Protocol):
    """Loop 机制层唯一事实生产门面。"""

    def append_catalog(self, event: SessionCatalogEvent, *, actor: str) -> AppendReceipt: ...

    def publish_ep(
        self,
        ep: SpineExecutionPoint,
        payload: Mapping[str, Any],
        *,
        actor: str,
    ) -> AppendReceipt: ...

    def append_surface(
        self,
        event_type: str,
        data: Mapping[str, Any],
        *,
        actor: str,
        surface_op: str = "append",
        visibility: str = "model",
    ) -> AppendReceipt: ...

    def append_diagnostic(self, diag: DiagnosticFact) -> AppendReceipt | None: ...


__all__ = [
    "AppendReceipt",
    "DiagnosticFact",
    "FactGateway",
    "SessionCatalogEvent",
    "SpineExecutionPoint",
]
