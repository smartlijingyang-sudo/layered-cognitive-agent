"""Session spine handles: AgentRegistry + CommandGateway + projections.

The session spine is gateway infrastructure, not part of the harness
profile. It is constructed at ``create_app()`` time, but the cordis
ctx it hands to live agent builders is resolved **per call** from
``app.state.ctx`` — which is set by the lifespan after the harness
profile boots.

This decouples session spine construction from profile boot: the
spine is wired up eagerly so request handlers can find it on
``app.state``, but the ctx it provides comes from the boot-time
plugin tree when each session is created.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from lca.contracts.capabilities import (
    SESSION_COMMAND_LEDGER,
    SESSION_LIVE_BUILDER,
    SESSION_PERSISTENCE_FACTORY,
    SESSION_PROJECTION_REGISTRY_FACTORY,
)
from lca.contracts.harness.agent import SessionLiveBuilder
from lca.contracts.harness.projection import (
    ProjectionChange,
    ProjectionDefinition,
    ProjectionSnapshot,
    SessionProjectionRegistry,
    SessionProjectionRegistryFactory,
)
from lca.contracts.harness.session import SessionEvent
from lca.contracts.protocols.session_command_ledger import SessionCommandLedger
from lca.contracts.protocols.session_persistence import SessionPersistenceFactory
from lca.harness.agent.registry import AgentRegistry
from lca.harness.command.gateway import CommandGateway


class LazySessionProjectionRegistry(SessionProjectionRegistry):
    """Resolve the declared projection backend at its first Session operation."""

    def __init__(
        self,
        factory_provider: Callable[[], SessionProjectionRegistryFactory],
    ) -> None:
        self._factory_provider = factory_provider
        self._delegate_registry: SessionProjectionRegistry | None = None
        self._pending_listeners: list[Callable[[ProjectionChange], None]] = []

    def _delegate(self) -> SessionProjectionRegistry:
        if self._delegate_registry is None:
            self._delegate_registry = self._factory_provider().create()
            for listener in self._pending_listeners:
                self._delegate_registry.subscribe_changes(listener)
            self._pending_listeners.clear()
        return self._delegate_registry

    def register(self, definition: ProjectionDefinition) -> None:
        self._delegate().register(definition)

    def bind_session(self, session_id: str) -> None:
        self._delegate().bind_session(session_id)

    def on_event(self, event: SessionEvent) -> None:
        self._delegate().on_event(event)

    def snapshot(self, session_id: str) -> ProjectionSnapshot:
        return self._delegate().snapshot(session_id)

    def subscribe_changes(self, listener: Callable[[ProjectionChange], None]) -> None:
        if self._delegate_registry is None:
            self._pending_listeners.append(listener)
        else:
            self._delegate_registry.subscribe_changes(listener)

    def replay(self, session_id: str, events: list[SessionEvent]) -> None:
        self._delegate().replay(session_id, events)


def bind_session_spine(
    *,
    sessions_dir: Path,
    ctx_provider: Callable[[], Any | None],
    live_builder_provider: Callable[[], SessionLiveBuilder],
    persistence_factory_provider: Callable[[], SessionPersistenceFactory],
    projection_registry_factory_provider: Callable[[], SessionProjectionRegistryFactory],
    command_ledger_provider: Callable[[], SessionCommandLedger],
) -> tuple[AgentRegistry, CommandGateway, SessionProjectionRegistry]:
    """Bind the session spine with a lazy ctx provider.

    Args:
        sessions_dir: Where session JSONL files live.
        ctx_provider: Callable returning the booted Cordis context for
            each session creation. The app composition root supplies this
            provider so builders always resolve the current booted tree.
        live_builder_provider: Callable resolving the booted Profile's declared
            Session Live Agent construction bridge.
        persistence_factory_provider: Callable resolving the booted Profile's
            declared Session fact-stream backend for create and resume paths.
        command_ledger_provider: Callable resolving the booted Profile's declared
            event-sourced idempotency policy for approval-resume commands.
        projection_registry_factory_provider: Callable resolving the booted
            Profile's declared Session projection storage and default views.

    Returns:
        ``(registry, command_gateway, projections)``. Bind them onto
        ``app.state`` and let request handlers use them.
    """
    projections = LazySessionProjectionRegistry(projection_registry_factory_provider)
    registry = AgentRegistry(
        sessions_dir=sessions_dir,
        projections=projections,
        live_builder_provider=live_builder_provider,
        ctx_provider=ctx_provider,
        persistence_factory_provider=persistence_factory_provider,
        command_ledger_provider=command_ledger_provider,
    )
    gateway = CommandGateway(registry, projections)
    return registry, gateway, projections


def session_live_builder_provider(
    ctx_provider: Callable[[], Any | None],
) -> Callable[[], SessionLiveBuilder]:
    """Resolve the booted Profile's Session Live Agent construction bridge."""

    def _provider() -> SessionLiveBuilder:
        ctx = ctx_provider()
        if ctx is None:
            raise RuntimeError("Session Live Builder requires a booted Profile context")
        return ctx.inject(SESSION_LIVE_BUILDER.key)

    return _provider


def session_projection_registry_factory_provider(
    ctx_provider: Callable[[], Any | None],
) -> Callable[[], SessionProjectionRegistryFactory]:
    """Resolve the booted Profile's Session projection factory only when needed."""

    def _provider() -> SessionProjectionRegistryFactory:
        ctx = ctx_provider()
        if ctx is None:
            raise RuntimeError("Session projection factory requires a booted Profile context")
        return ctx.inject(SESSION_PROJECTION_REGISTRY_FACTORY.key)

    return _provider


def session_command_ledger_provider(
    ctx_provider: Callable[[], Any | None],
) -> Callable[[], SessionCommandLedger]:
    """Resolve the Profile-selected durable command ledger only when needed."""

    def _provider() -> SessionCommandLedger:
        ctx = ctx_provider()
        if ctx is None:
            raise RuntimeError("Session command ledger requires a booted Profile context")
        return ctx.inject(SESSION_COMMAND_LEDGER.key)

    return _provider


def session_persistence_factory_provider(
    ctx_provider: Callable[[], Any | None],
) -> Callable[[], SessionPersistenceFactory]:
    """Resolve the booted Profile's Session backend only when it is needed."""

    def _provider() -> SessionPersistenceFactory:
        ctx = ctx_provider()
        if ctx is None:
            raise RuntimeError("Session persistence factory requires a booted Profile context")
        return ctx.inject(SESSION_PERSISTENCE_FACTORY.key)

    return _provider


def ctx_provider_from_app(app: Any) -> Callable[[], Any | None]:
    """Build a ctx_provider that reads ``app.state.ctx``.

    Use this when constructing the session spine: pass the returned
    callable to :func:`bind_session_spine`. The callable resolves
    ``app.state.ctx`` on each call, so it picks up the booted ctx
    after the lifespan runs without holding a stale reference.
    """

    def _provider() -> Any | None:
        return getattr(app.state, "ctx", None)

    return _provider
