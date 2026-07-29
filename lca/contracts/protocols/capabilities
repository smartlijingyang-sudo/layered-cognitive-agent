"""L2 Runtime.configure() 所需的可选能力协议（ADR-0017）。
把原先散落在 configure() 里的 hasattr 字符串探测收敛成具名、
runtime_checkable 的 Protocol，使能力契约可被 mypy 校验、可被 grep 发现。
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
