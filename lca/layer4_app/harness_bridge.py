"""Layer-4 factory that builds a LiveAgent for the harness registry.

Resolves the agent loop builder from the plugin scope (``agent_loop`` seam).
If the scope provides a loop builder, it is used; otherwise falls back to
the default cognitive loop builder from ``lca.plugins.loop_cognitive``.
"""

from __future__ import annotations

from typing import Any

from lca.harness.agent.handle import OwnerAgentHandle
from lca.harness.session.inbox import Inbox
from lca.harness.session.store import SessionStore


def build_live_agent(
    store: SessionStore,
    inbox: Inbox,
    identity_id: str,
    options: dict[str, Any] | None,
    plugin_scope: Any | None,
) -> OwnerAgentHandle:
    """Build a LiveAgent by resolving the loop builder from plugin scope.

    Resolution order:
    1. plugin_scope.resolve("agent_loop") — the plugin-driven path
    2. Fallback to default cognitive loop builder (for when scope is None
       or doesn't provide agent_loop)

    This makes the agent loop fully swappable through YAML configuration:
    replace the loop plugin in the profile to change the execution engine.
    """
    builder = _resolve_loop_builder(plugin_scope)
    return builder(store, inbox, identity_id, options, plugin_scope)


def _resolve_loop_builder(plugin_scope: Any | None) -> Any:
    """Resolve the agent loop builder from plugin scope or fallback."""
    if plugin_scope is not None:
        try:
            builder = plugin_scope.resolve("agent_loop")
            if callable(builder):
                return builder
        except (KeyError, AttributeError):
            pass

    # Fallback: import the default cognitive loop builder directly
    from lca.plugins.loop_cognitive import build_cognitive_live_agent

    return build_cognitive_live_agent
