"""GateChainComposer Protocol（ADR-0074：可定制决策门链组合）。

当前 ``lca/cognition/brain/decision_gates/__init__.py`` 中硬编码了
``build_workspace_agent_gate()`` 函数（lines 29-52），固定了 5-gate 链顺序。
Gates 本身是插件，但链组合（chain composition）不是。本 Protocol 将链组合
抽象为可替换 seam：profile 通过 ``ctx.provide("gate_chain_composer", ...)``
注入自定义实现，可改变 gate 顺序、增删 gate、或完全替换默认 5-gate 链。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.protocols.think.cognition import DecisionGate


@runtime_checkable
class GateChainComposer(Protocol):
    """Compose a chain of DecisionGates.

    ADR-0074: Extract hard-coded build_workspace_agent_gate into pluggable Protocol.
    Default implementation returns the standard 5-gate chain; profile can replace via
    ctx.provide("gate_chain_composer", ...) to customize gate ordering/composition.
    """

    def compose(self) -> DecisionGate:
        """Compose and return a DecisionGate chain."""
        ...


__all__ = ["GateChainComposer"]
