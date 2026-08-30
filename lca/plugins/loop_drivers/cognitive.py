"""LCA-owned factory for a cognitive live agent.

Gateway-specific run-driver registration lives in
:mod:`gateway.plugins.cognitive_loop`. This module owns only the LCA
live-agent factory.

A Session Spine agent is always assembled from its already-booted Profile.
The factory therefore fails closed when the Profile scope or its LLM resolver
is absent; it never fabricates a default context or silently swaps in a Mock
LLM for a production request.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from lca.contracts.capabilities import (
    SESSION_FOLLOWUP_POLICY,
    SESSION_TURN_CONTROLLER_FACTORY,
)
from lca.contracts.mechanisms.capability import MissingCapabilityError, require_capability
from lca.contracts.protocols.session_turn import (
    SessionFollowupPolicy,
    SessionTurnController,
    SessionTurnControllerFactory,
)

if TYPE_CHECKING:
    from cordis import Context

    from lca.contracts.protocols import LLMAdapter
    from lca.harness.session.inbox import Inbox
    from lca.harness.session.store import SessionStore


class SessionLoopAssemblyError(RuntimeError):
    """Raised when a Session Spine loop lacks a declared production dependency."""


def build_cognitive_live_agent(
    store: SessionStore,
    inbox: Inbox,
    identity_id: str,
    options: dict[str, Any] | None,
    cordis_ctx: Context | None,
) -> object:
    """Build a LiveAgent from one booted Profile scope.

    ``agent_options.llm`` is an explicit fixture seam. Production callers omit
    it and receive the adapter selected by the Profile's ``llm_resolver``.
    """

    if cordis_ctx is None:
        raise SessionLoopAssemblyError(
            "Session Spine requires a booted Profile scope; implicit default contexts are forbidden."
        )

    opts = options or {}
    llm = _resolve_llm(opts, cordis_ctx)
    tools = opts.get("tools") or ()

    from lca.harness.agent.handle import OwnerAgentHandle
    from lca.application.api import Agent
    from lca.application.harness_live import CognitiveLiveAgent

    agent = Agent(
        role=opts.get("role", identity_id),
        goal="",
        backstory="",
        tools=tuple(tools),
        llm=llm,
        scope=cordis_ctx,
    )
    live = CognitiveLiveAgent(
        agent=agent,
        store=store,
        inbox=inbox,
        identity_id=identity_id,
        turn_controller=_resolve_turn_controller(cordis_ctx, identity_id),
        followup_policy=_resolve_followup_policy(cordis_ctx),
    )
    return OwnerAgentHandle(live)


def _resolve_turn_controller(scope: Context, session_id: str) -> SessionTurnController:
    """Build the Profile-selected controller that owns this Session's live task."""

    try:
        factory = cast(
            "SessionTurnControllerFactory",
            require_capability(scope, SESSION_TURN_CONTROLLER_FACTORY.key),
        )
    except MissingCapabilityError as exc:
        raise SessionLoopAssemblyError(
            "Session Spine requires a Profile providing 'session_turn_controller_factory'."
        ) from exc
    controller = factory.create(session_id=session_id)
    if not isinstance(controller, SessionTurnController):
        raise SessionLoopAssemblyError(
            "Session Spine 'session_turn_controller_factory' must create a SessionTurnController."
        )
    return controller


def _resolve_followup_policy(scope: Context) -> SessionFollowupPolicy:
    """Resolve the pure, Profile-owned concurrent follow-up policy."""

    try:
        policy = require_capability(scope, SESSION_FOLLOWUP_POLICY.key)
    except MissingCapabilityError as exc:
        raise SessionLoopAssemblyError(
            "Session Spine requires a Profile providing 'session_followup_policy'."
        ) from exc
    if not isinstance(policy, SessionFollowupPolicy):
        raise SessionLoopAssemblyError(
            "Session Spine 'session_followup_policy' must implement SessionFollowupPolicy."
        )
    return policy


def _resolve_llm(options: dict[str, Any], scope: Context) -> LLMAdapter:
    """Resolve one explicit fixture LLM or the Profile-owned production adapter."""

    configured = options.get("llm")
    if configured is not None:
        return cast("LLMAdapter", configured)

    try:
        resolver = scope.inject("llm_resolver")
    except (AttributeError, KeyError) as exc:
        raise SessionLoopAssemblyError(
            "Session Spine requires an explicit agent_options.llm fixture or a Profile "
            "providing 'llm_resolver'."
        ) from exc

    resolve = getattr(resolver, "resolve", None)
    if not callable(resolve):
        raise SessionLoopAssemblyError("Session Spine 'llm_resolver' must expose resolve().")
    return cast("LLMAdapter", resolve())


__all__ = [
    "SessionLoopAssemblyError",
    "build_cognitive_live_agent",
]
