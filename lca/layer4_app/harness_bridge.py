"""Bridge a booted Cordis loop provider into the Session Spine.

The agent loop is provided by Tier-3 plugins registered at the ``agent_loop``
key.  Session Spine construction must resolve that provider from the booted
plugin tree for every live agent.  A missing or invalid provider is an
assembly error, never permission to silently select a concrete cognitive loop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from lca.harness.agent.handle import OwnerAgentHandle
    from lca.harness.session.inbox import Inbox
    from lca.harness.session.store import SessionStore


class MissingAgentLoopProviderError(RuntimeError):
    """Raised when a Session Spine agent lacks a declared loop provider."""


def build_live_agent(
    store: SessionStore,
    inbox: Inbox,
    identity_id: str,
    options: dict[str, Any] | None,
    cordis_ctx: Any | None = None,
) -> OwnerAgentHandle:
    """Build a LiveAgent using the ``agent_loop`` provider in Cordis context.

    A production Session Spine is driven by its resolved Profile and Bundle.
    Consequently, it requires a booted Cordis context exposing a callable
    ``agent_loop`` provider. Tests that need a concrete loop must inject that
    builder explicitly instead of depending on this composition bridge.
    """
    builder = _resolve_loop_builder(cordis_ctx)
    return cast(
        "OwnerAgentHandle",
        builder(store, inbox, identity_id, options, cordis_ctx),
    )


def _resolve_loop_builder(cordis_ctx: Any | None) -> Any:
    """Resolve the declared loop provider or fail closed during assembly."""
    if cordis_ctx is None:
        raise MissingAgentLoopProviderError(
            "Session Spine requires a booted Cordis context with an 'agent_loop' provider."
        )

    try:
        builder = cordis_ctx.inject("agent_loop")
    except (KeyError, AttributeError) as exc:
        raise MissingAgentLoopProviderError(
            "Session Spine requires the active Profile to provide 'agent_loop'."
        ) from exc

    if not callable(builder):
        raise MissingAgentLoopProviderError("Session Spine 'agent_loop' provider must be callable.")
    return builder
