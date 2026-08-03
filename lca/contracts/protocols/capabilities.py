"""Optional capability protocols used outside composition mutation.

Closed object graph (ADR-0029): channel / gate / shared memory / reasoner
are construction-time dependencies — not post-hoc bind/install slots.

``HasHooks`` remains for lifecycle registration on an already-built runtime.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.mechanisms import HookRegistry


@runtime_checkable
class HasHooks(Protocol):
    """Runtime 若暴露 HookRegistry 供 Agent 注册生命周期钩子，实现此协议。"""

    hooks: HookRegistry
