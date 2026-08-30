"""Plan-bound composition for perceive, memory, state, and stop clusters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lca.contracts.capabilities import MEMORY, STATE_STORE
from lca.contracts.harness.composer import AgentCompositionRequest, AgentGraphContribution
from lca.contracts.mechanisms.capability import require_capability
from lca.plugins.composer.internal.perceive import (
    build_perceive_hub,
    resolve_memory,
    resolve_state_store,
    resolve_stop_policy,
)
from lca.plugins.composer.internal.team import resolve_observability

if TYPE_CHECKING:
    from cordis import Context


class PerceiveComposer:
    """Compose only the perceive, memory, state, and stop clusters.

    Keeping these cohesive cognitive and runtime selections together prevents
    execution and organization concerns from widening this module's interface.
    All choices remain explicit fields or declared capabilities on the booted
    scope, so profile substitution stays local to this seam.
    """

    key = "perceive"

    def compose_agent(
        self, request: AgentCompositionRequest, scope: Context
    ) -> AgentGraphContribution:
        """Return the graph contribution selected for context and state handling."""

        observability = resolve_observability(request.spec, scope)
        memory = resolve_memory(
            request.spec.memory, request.shared_store, require_capability(scope, MEMORY.key)
        )
        state_store = resolve_state_store(
            request.spec.state_store, require_capability(scope, STATE_STORE.key)
        )
        journal_store = require_capability(scope, "journal_store")()
        stop_policy = resolve_stop_policy(scope=scope)
        perceive_hub = build_perceive_hub(
            memory,
            store=journal_store,
            scope=scope,
            action_scope=request.action_scope,
        )
        return AgentGraphContribution(
            brain=None,
            body=None,
            memory=memory,
            state_store=state_store,
            perceive_hub=perceive_hub,
            hooks=None,
            observability=observability,
            llm=None,
            phase_capabilities={"stop_policy": stop_policy},
            metadata={"composer": self.key},
        )


__all__ = ["PerceiveComposer"]
