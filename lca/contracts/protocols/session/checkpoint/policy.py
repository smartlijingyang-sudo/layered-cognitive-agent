"""Session durability checkpoint policy — contracts seam (ADR-0191 Wave A3).

Implementation: ``lca.plugins.session.checkpoint_policy`` capability
``session.checkpoint.policy``. Cognition awaits these boundaries via
``lca.infrastructure.session.bindings``; contracts layer defines only
the passive call surface and failure type re-export.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.protocols.session.persistence.service import CheckpointFailure


@runtime_checkable
class FlushableSession(Protocol):
    """Checkpoint target: async ``flush()`` returning per-listener results."""

    async def flush(self) -> object: ...


@runtime_checkable
class SessionCheckpointPolicyProtocol(Protocol):
    """Fail-closed durability barriers before LLM dispatch and tool body."""

    async def before_model_request(self, session: FlushableSession) -> None: ...

    async def before_tool_side_effect(self, session: FlushableSession) -> None: ...

    async def at_step_boundary(self, session: FlushableSession) -> None: ...


__all__ = [
    "CheckpointFailure",
    "FlushableSession",
    "SessionCheckpointPolicyProtocol",
]
