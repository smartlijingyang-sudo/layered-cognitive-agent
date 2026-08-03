"""可选能力协议（ADR-0017）。

把组件的可选绑定能力（channel / shared_memory / replaceable reasoner）
收敛成具名、runtime_checkable 的 Protocol，
使能力契约可被 mypy 校验、可被 grep 发现。

由组装层（TeamOrchestrator / SupervisorBinder）通过 isinstance 检查直接调用，
不再经过 Runtime.configure() 间接分发。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.mechanisms import HookRegistry
from lca.contracts.protocols.cognition import Reasoner
from lca.contracts.protocols.infra import AgentTransport


@runtime_checkable
class HasChannel(Protocol):
    """Body 若支持委派/handoff，需实现此协议以接收 Transport。"""

    def bind_channel(self, transport: AgentTransport) -> None: ...


@runtime_checkable
class HasSharedMemory(Protocol):
    """MemorySystem 若支持团队共享记忆（CoALA），实现此协议。"""

    def bind_shared_memory(self, store: object) -> None: ...


@runtime_checkable
class HasBrainBodyMemory(Protocol):
    """Runtime 若暴露 body / brain / memory 供组合期能力绑定，实现此协议。"""

    body: object
    brain: object
    memory: object


@runtime_checkable
class HasReplaceableReasoner(Protocol):
    """Brain 若允许组装期替换 Reasoner（supervisor 认知绑定），实现此协议。"""

    reasoner: Reasoner


@runtime_checkable
class HasHooks(Protocol):
    """Runtime 若暴露 HookRegistry 供 Agent 注册生命周期钩子，实现此协议。"""

    hooks: HookRegistry
