"""AgentLoop — Service that creates and manages ReactLoopAgent instances.

1:1 port of ``@deepseek-ai/dsh-agent-loop/index.ts``.

Handles agent factory registration, create/resume flows, configured-agent
identity validation, and abort/teardown coordination.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from lca.layer0_infra.dsh_core.agent import (
    AgentOptions,
    CreateAgentOptions,
    ResumeAgentOptions,
)
from lca.layer0_infra.dsh_core.agent_loop.agent import ReactLoopAgent
from lca.layer0_infra.dsh_core.agent_loop.constants import DEFAULT_MAX_PARALLEL_TOOL_CALLS
from lca.layer0_infra.dsh_core.session import Session, SessionId


@dataclass
class AgentLoopConfig:
    """Configuration for the AgentLoop service."""

    max_parallel_tool_calls: int = DEFAULT_MAX_PARALLEL_TOOL_CALLS


@dataclass
class ConfiguredAgentIdentity:
    """Pre-configured agent identity for launcher-driven creation."""

    agent_id: str
    profile: str
    options: AgentOptions | None = None


AgentFactory = Callable[["AgentLoop", AgentOptions], ReactLoopAgent]


@dataclass
class FactoryOwnership:
    """Tracks live agents and teardown state for one factory."""

    live_agents: set[Callable[[], Awaitable[None]]] = field(default_factory=set)
    teardown: asyncio.Event = field(default_factory=asyncio.Event)
    startup_tasks: set[Awaitable[Any]] = field(default_factory=set)


INACTIVE_STATES = {"unloading", "disposed", "failed"}


async def race_abort(awaitable: Awaitable[Any], signal: asyncio.Event) -> Any:
    """Race an awaitable against an abort signal."""
    if signal.is_set():
        raise asyncio.CancelledError()
    abort_task = asyncio.create_task(signal.wait())
    try:
        done, _ = await asyncio.wait(
            [asyncio.create_task(awaitable), abort_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        if abort_task in done:
            for t in done:
                if t is not abort_task:
                    t.cancel()
            raise asyncio.CancelledError()
        result = next(iter(done)).result()
        abort_task.cancel()
        return result
    finally:
        if not abort_task.done():
            abort_task.cancel()


def race_abort_call(fn: Callable[..., Any], *args: Any, signal: asyncio.Event, **kwargs: Any) -> Any:
    """Synchronous variant of race_abort."""
    if signal.is_set():
        raise asyncio.CancelledError()
    return fn(*args, **kwargs)


class AgentLoop:
    """Service that creates and manages ReactLoopAgent instances."""

    def __init__(self, ctx: Any, config: AgentLoopConfig | None = None) -> None:
        self._ctx = ctx
        self._config = config or AgentLoopConfig()
        self._factory: AgentFactory | None = None
        self._ownership = FactoryOwnership()
        self._configured_identities: list[ConfiguredAgentIdentity] = []

    def set_factory(self, factory: AgentFactory) -> Callable[[], None]:
        """Register an agent factory. Returns a disposer."""
        self._factory = factory
        return lambda: self._set_factory(None) if self._factory is factory else None

    def _set_factory(self, factory: AgentFactory | None) -> None:
        self._factory = factory

    @property
    def max_parallel_tool_calls(self) -> int:
        return self._config.max_parallel_tool_calls

    def configure_agents(self, identities: list[ConfiguredAgentIdentity]) -> None:
        """Register configured agent identities for launcher-driven creation."""
        self._configured_identities = list(identities)

    def validate_configured_agents(self) -> None:
        """Validate configured agent identities for conflicts."""
        seen: set[str] = set()
        for identity in self._configured_identities:
            if identity.agent_id in seen:
                raise ValueError(f"duplicate configured agent id: {identity.agent_id}")
            seen.add(identity.agent_id)

    async def create(
        self,
        agent_id: SessionId | None = None,
        options: CreateAgentOptions | None = None,
        *,
        setup: Callable[[ReactLoopAgent], Awaitable[Any]] | None = None,
    ) -> ReactLoopAgent:
        """Create and start a new ReactLoopAgent."""
        if self._factory is None:
            raise RuntimeError("AgentLoop.create: no factory registered (call set_factory first)")
        await self._build_session(agent_id, options)
        agent_options = AgentOptions(
            provider=getattr(options, "provider", None) if options else None,
            model=getattr(options, "model", None) if options else None,
            max_tokens=getattr(options, "max_tokens", None) if options else None,
        )
        agent = self._factory(self, agent_options)
        if setup is not None:
            await setup(agent)
        return agent

    async def resume(
        self,
        agent_id: SessionId,
        options: ResumeAgentOptions | None = None,
        *,
        setup: Callable[[ReactLoopAgent], Awaitable[Any]] | None = None,
    ) -> ReactLoopAgent:
        """Resume an existing ReactLoopAgent from its session log."""
        if self._factory is None:
            raise RuntimeError("AgentLoop.resume: no factory registered")
        await self._load_session(agent_id)
        agent_options = AgentOptions(
            provider=getattr(options, "provider", None) if options else None,
            model=getattr(options, "model", None) if options else None,
        )
        agent = self._factory(self, agent_options)
        if setup is not None:
            await setup(agent)
        return agent

    async def restore_or_create_configured(self) -> list[ReactLoopAgent]:
        """Restore or create all configured agents."""
        self.validate_configured_agents()
        agents: list[ReactLoopAgent] = []
        for identity in self._configured_identities:
            existing = await self._try_load_session(identity.agent_id)
            if existing is not None:
                agent = await self.resume(identity.agent_id)
            else:
                agent = await self.create(
                    identity.agent_id,
                    CreateAgentOptions(profile=identity.profile, meta={"preset": identity.profile}),
                )
            agents.append(agent)
        return agents

    async def apply_launcher_identities(
        self,
        identities: list[ConfiguredAgentIdentity],
    ) -> list[ReactLoopAgent]:
        """Apply launcher-supplied identities (replaces configured set)."""
        self.configure_agents(identities)
        return await self.restore_or_create_configured()

    def track_live(self, dispose: Callable[[], Awaitable[None]]) -> None:
        """Track a live agent's dispose callback."""
        self._ownership.live_agents.add(dispose)

    def untrack_live(self, dispose: Callable[[], Awaitable[None]]) -> None:
        """Remove a tracked dispose callback."""
        self._ownership.live_agents.discard(dispose)

    async def _build_session(
        self,
        agent_id: SessionId | None,
        options: CreateAgentOptions | None,
    ) -> Session:
        """Build a fresh session for a new agent."""
        from lca.layer0_infra.dsh_core.session import SessionHeader

        sid = agent_id or f"session-{uuid_str()}"
        header = SessionHeader(
            version=0,
            id=sid,
            created_at=0,
        )
        from lca.layer0_infra.dsh_core.session import Session
        return Session.create(sid, [], header)

    async def _load_session(self, agent_id: SessionId) -> Session:
        """Load an existing session from the store."""

        store = getattr(self._ctx, "sessions", None)
        if store is None:
            raise RuntimeError("AgentLoop: no sessions store available")
        session = store.get(agent_id)
        if session is None:
            raise KeyError(f"session {agent_id} not found")
        return session

    async def _try_load_session(self, agent_id: SessionId) -> Session | None:
        try:
            return await self._load_session(agent_id)
        except KeyError:
            return None


def uuid_str() -> str:
    import uuid

    return uuid.uuid4().hex[:12]
