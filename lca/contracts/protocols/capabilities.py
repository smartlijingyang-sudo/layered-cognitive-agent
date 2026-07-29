"""可选能力协议（ADR-0017）。

把组件的可选绑定能力（transport / roster / shared_memory）
收敛成具名、runtime_checkable 的 Protocol，
使能力契约可被 mypy 校验、可被 grep 发现。

由组装层（TeamOrchestrator / Supervisor）通过 isinstance 检查直接调用，
不再经过 Runtime.configure() 间接分发。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.protocols.infra import AgentTransport


@runtime_checkable
class TransportBindable(Protocol):
    """Body 若支持委派/handoff，需实现此协议以接收 Transport。"""

    def bind_transport(self, transport: AgentTransport) -> None: ...


@runtime_checkable
class RosterAware(Protocol):
    """Brain 若需要感知队友花名册（hierarchical 编排），实现此协议。"""

    def set_team_roster(self, roster_desc: str) -> None: ...


@runtime_checkable
class SharedStoreBindable(Protocol):
    """MemorySystem 若支持团队共享记忆（CoALA），实现此协议。"""

    def bind_shared_store(self, store: object) -> None: ...
