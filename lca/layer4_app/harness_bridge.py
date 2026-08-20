"""Bridge between LCA harness and the cordis plugin tree.

The agent loop is provided by Tier-3 plugins registered at the `agent_loop`
key. Resolution path: `cordis_ctx.inject("agent_loop")` — falls back to
the default cognitive loop builder if not provided.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from lca.harness.agent.handle import OwnerAgentHandle
    from lca.harness.session.inbox import Inbox
    from lca.harness.session.store import SessionStore


def build_live_agent(
    store: SessionStore,
    inbox: Inbox,
    identity_id: str,
    options: dict[str, Any] | None,
    cordis_ctx: Any | None = None,
    *,
    plugin_scope: Any | None = None,  # DEPRECATED: use cordis_ctx
) -> OwnerAgentHandle:
    """Build a LiveAgent by resolving the loop builder from cordis context.

    Resolution order:
    1. cordis_ctx.inject("agent_loop") — the plugin-driven path
    2. Fallback to default cognitive loop builder (for when ctx is None
       or doesn't provide agent_loop)

    The agent loop is fully swappable through YAML configuration:
    replace the loop plugin in the profile to change the execution engine.
    """
    ctx = cordis_ctx if cordis_ctx is not None else plugin_scope
    builder = _resolve_loop_builder(ctx)
    return cast(OwnerAgentHandle, builder(store, inbox, identity_id, options, ctx))


def _resolve_loop_builder(cordis_ctx: Any | None) -> Any:
    """Resolve the agent loop builder from cordis context or fallback."""
    if cordis_ctx is not None:
        try:
            builder = cordis_ctx.inject("agent_loop")
            if callable(builder):
                return builder
        except (KeyError, AttributeError):
            pass

    # Fallback: import the default cognitive loop builder directly
    from lca.plugins.loop_cognitive import build_cognitive_live_agent

    return build_cognitive_live_agent
