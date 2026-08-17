"""1:1 port of ``@deepseek-ai/dsh-agent/index.ts``.

Agent service: live registry, factory delegation, and process-local
initiator scope.  Concrete creation and driving belong to the loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from lca.layer0_infra.dsh_core.agent.dispatch import (
    agent_carrier,
    emit_agent_event,
)
from lca.layer0_infra.dsh_core.agent.runtime_types import (
    Agent,
    AgentOptions,
)
from lca.layer0_infra.dsh_core.session.types import (
    SessionEvent,
    SessionId,
)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Setup types
# ---------------------------------------------------------------------------


class AgentSetupCommit(Protocol):
    """Synchronous finalizer returned by unpublished Agent setup."""

    def commit(self) -> None:
        """Validate and commit the prepared setup immediately before publication.

        Raises:
            Exception: when publication must roll the unpublished Agent back.
        """
        ...


AgentSetup = Callable[[Any], "AgentSetupCommit | None"]
"""Compose an unpublished Agent scope and optionally return its publication commit."""


# ---------------------------------------------------------------------------
# CreateAgentOptions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CreateAgentOptions:
    """Options for programmatically creating an agent through the registry factory."""

    session_id: SessionId
    """The live agent/session identity."""
    meta: dict[str, Any] | None = None
    """Session creation metadata (cwd, parentSession, seedLength, origin, …)."""
    seed: tuple[SessionEvent, ...] | None = None
    """Initial replay/fork history."""
    agent_options: AgentOptions | None = None
    """Per-agent options (model, …)."""
    signal: Any = None
    """Optional creation-only cancellation signal."""
    setup: AgentSetup | None = None
    """Creation-time composition of the agent's scoped world."""


# ---------------------------------------------------------------------------
# ResumeAgentOptions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResumeAgentOptions:
    """Options for resuming an agent on a persisted session."""

    resume_session_id: SessionId
    """The persisted session id to load and use as the live agent/session identity."""
    agent_options: AgentOptions | None = None
    """Per-agent options (model, …)."""
    signal: Any = None
    """Optional creation-only cancellation signal."""
    setup: AgentSetup | None = None
    """Resume-time composition of the agent's fresh scoped world."""


# ---------------------------------------------------------------------------
# AgentHandle
# ---------------------------------------------------------------------------


class AgentHandle(Protocol):
    """An owned agent plus its disposer, returned by create / resume."""

    @property
    def agent(self) -> Agent: ...

    async def dispose(self) -> None: ...


# ---------------------------------------------------------------------------
# AgentFactory
# ---------------------------------------------------------------------------


class AgentFactory(Protocol):
    """The agent-creation factory the loop implementation provides to the registry."""

    async def create_agent(
        self,
        owner_ctx: Any,
        options: CreateAgentOptions,
    ) -> AgentHandle: ...

    async def resume(
        self,
        owner_ctx: Any,
        options: ResumeAgentOptions,
    ) -> AgentHandle: ...


# ---------------------------------------------------------------------------
# Error messages
# ---------------------------------------------------------------------------

_NO_FACTORY_MESSAGE = "no agent factory registered (load an agent-loop plugin)"
_NO_INITIATOR_MESSAGE = "no initiating agent is active"
_DISPOSED_INITIATOR_MESSAGE = "agent initiator scope is disposed"


# ---------------------------------------------------------------------------
# Internal entry
# ---------------------------------------------------------------------------


@dataclass
class _AgentEntry:
    """All mutable lifecycle state for one exact registry entry."""

    id: SessionId
    agent: Agent
    owner: Agent | None
    carrier: Any
    announced: bool = False
    announcing: bool = False
    detach_requested: bool = False


@dataclass
class _InitiatorRun:
    """One tracked boundary plus its inherited nesting chain."""

    active: bool = True
    parent: _InitiatorRun | None = None


# ---------------------------------------------------------------------------
# AgentRegistry
# ---------------------------------------------------------------------------


class AgentRegistry:
    """Agent service: tracks live agents and carries the initiating Agent through
    one process-local asynchronous driver chain.

    Initiator methods provide same-process causal attribution only.  Ambient
    presence is neither liveness proof nor authorization; subjects and owners
    remain explicit, as does identity at worker, process, persistence, and wire
    boundaries.

    In Python, the initiator scope is implemented with :mod:`contextvars`
    (equivalent to TS ``AsyncLocalStorage``).
    """

    def __init__(self, ctx: Any) -> None:
        self._ctx = ctx
        self._store: dict[SessionId, _AgentEntry] = {}
        self._factory: AgentFactory | None = None

        # Initiator scope — contextvars-based (AsyncLocalStorage equivalent)
        import contextvars

        self._initiator_var: contextvars.ContextVar[Agent | None] = contextvars.ContextVar(
            "agent_initiator", default=None
        )
        self._initiator_run_var: contextvars.ContextVar[_InitiatorRun | None] = (
            contextvars.ContextVar("agent_initiator_run", default=None)
        )
        self._initiator_state: str = "active"  # 'active' | 'closing' | 'disposed'
        self._active_initiator_runs: int = 0
        self._initiator_drain: asyncio.Future[None] | None = None
        self._initiator_disposal: asyncio.Task[None] | None = None

    # -- Initiator scope -------------------------------------------------------

    def current_initiator(self) -> Agent | None:
        """Read the Agent that initiated the inherited asynchronous driver chain.

        Returns the inherited Agent, or ``None`` outside an initiator boundary
        and inside an explicit clearing boundary.

        Raises:
            RuntimeError: when this service instance has been disposed.
        """
        self._assert_initiators_readable()
        return self._initiator_var.get()

    def require_initiator(self) -> Agent:
        """Read the initiating Agent and fail when no initiator boundary is active.

        Raises:
            RuntimeError: when no initiator is active or this service instance has been disposed.
        """
        agent = self.current_initiator()
        if agent is None:
            raise RuntimeError(_NO_INITIATOR_MESSAGE)
        return agent

    def with_initiator(self, agent: Agent, operation: Callable[[], T]) -> T:
        """Run an operation with one exact Agent as its process-local initiator.

        Raises:
            RuntimeError: when the initiator scope is closing/disposed, or when operation throws.
        """
        return self._run_with_initiator(agent, operation)

    def without_initiator(self, operation: Callable[[], T]) -> T:
        """Run an operation inside a boundary that hides any inherited initiating Agent.

        Raises:
            RuntimeError: when the initiator scope is closing/disposed, or when operation throws.
        """
        return self._run_with_initiator(None, operation)  # type: ignore[arg-type]

    # -- Factory ---------------------------------------------------------------

    def set_factory(self, factory: AgentFactory) -> Callable[[], None]:
        """Register the agent-creation factory.

        Throws if a factory is already registered.  Returns the disposer; on
        dispose the factory slot is cleared.
        """
        if self._factory is not None:
            raise RuntimeError("an agent factory is already registered")
        self._factory = factory

        def dispose() -> None:
            self._factory = None

        return dispose

    def _require_factory(self) -> AgentFactory:
        if self._factory is None:
            raise RuntimeError(_NO_FACTORY_MESSAGE)
        return self._factory

    # -- Create / Resume -------------------------------------------------------

    async def create(self, options: CreateAgentOptions) -> AgentHandle:
        """Create and publish a new agent through the registered factory."""
        factory = self._require_factory()
        return await factory.create_agent(self._ctx, options)

    async def resume(self, options: ResumeAgentOptions) -> AgentHandle:
        """Load a persisted session and resume an agent on it through the registered factory."""
        factory = self._require_factory()
        return await factory.resume(self._ctx, options)

    # -- Register / Enter / Announce ------------------------------------------

    def register(self, agent: Agent) -> Callable[[], None]:
        """Register a live agent.

        Throws if an agent with the same id is already registered.
        Emits ``agent/created`` on registration and ``agent/disposed``
        when the calling fiber is disposed.

        Returns the disposer (idempotent, single-shot).
        """
        owner: Agent | None = getattr(self._ctx, "agent", None)
        detach = self.enter(agent, owner)
        self.announce(agent)

        def dispose() -> None:
            detach()

        return dispose

    def enter(self, agent: Agent, owner: Agent | None = None) -> Callable[[], None]:
        """Insert an already-constructed agent without announcing it.

        This is the advanced ordered-lifecycle primitive used by the async
        agent factory: it first completes setup while the agent is unpublished,
        then assigns the returned detach closure into its pre-installed
        composite teardown before calling :meth:`announce`.

        Returns an idempotent closure that removes this exact entry and emits
        ``agent/disposed`` with listener failures contained.
        """
        agent_id = agent.id
        # Validate id consistency (TS: agent.id !== agent.session.id)
        session_obj = getattr(agent, "session", None)
        session_id = getattr(session_obj, "id", None) if session_obj is not None else None
        if session_id is not None and agent_id != session_id:
            raise RuntimeError(f'agent id "{agent_id}" does not match session id "{session_id}"')

        carrier = agent_carrier(agent)

        if agent_id in self._store:
            raise RuntimeError(f'agent "{agent_id}" is already registered')

        entry = _AgentEntry(
            id=agent_id,
            agent=agent,
            owner=owner,
            carrier=carrier,
        )
        self._store[agent_id] = entry
        entered = True

        def detach() -> None:
            nonlocal entered
            if not entered:
                return
            entered = False
            if entry.announcing:
                entry.detach_requested = True
                return
            self._detach_entered(entry)

        return detach

    def _detach_entered(self, entry: _AgentEntry) -> None:
        """Remove one exact entered agent and emit its paired disposal when announced."""
        entry.detach_requested = False
        if self._store.get(entry.id) is not entry:
            return
        del self._store[entry.id]
        if not entry.announced:
            return
        self._emit_disposed(entry)

    def _emit_disposed(self, entry: _AgentEntry) -> None:
        """Emit the paired disposal edge through the entry's stable carrier."""
        try:
            emit_agent_event(self._ctx, entry.agent, "agent/disposed", {"agent": entry.agent})
        except Exception as exc:
            logger = getattr(self._ctx, "logger", None)
            if logger is not None:
                with contextlib.suppress(Exception):
                    logger.warning(
                        'agent "%s": agent/disposed listener threw: %s',
                        entry.id,
                        exc,
                    )

    def announce(self, agent: Agent) -> None:
        """Announce an agent previously inserted with :meth:`enter`.

        Raises:
            RuntimeError: if agent is not the exact live registry entry for its id,
                or its creation announcement already began.
        """
        entry = self._store.get(agent.id)
        if entry is None or entry.agent is not agent:
            raise RuntimeError(f'agent "{agent.id}" is not live in this registry')
        if entry.announced or entry.announcing:
            raise RuntimeError(f'agent "{entry.id}" was already announced')

        entry.announcing = True
        entry.announced = True
        try:
            emit_agent_event(self._ctx, agent, "agent/created", {"agent": agent})
        finally:
            entry.announcing = False
            if entry.detach_requested:
                self._detach_entered(entry)

    # -- Lookup ---------------------------------------------------------------

    def get(self, id: SessionId) -> Agent | None:
        """Look up a live agent.

        Returns the agent, or ``None`` when no live agent has that id.
        """
        entry = self._store.get(id)
        return entry.agent if entry is not None else None

    def is_owned_by(self, id: SessionId, owner: Agent) -> bool:
        """Test whether a live agent was created through one exact parent agent's scoped context."""
        entry = self._store.get(id)
        return entry is not None and entry.owner is owner

    def list(self) -> list[Agent]:
        """All live agents, in registration order."""
        return [entry.agent for entry in self._store.values()]

    def roots(self) -> list[Agent]:
        """All live top-level agents in registration order.

        A top-level agent was created without an owning agent context.
        """
        return [entry.agent for entry in self._store.values() if entry.owner is None]

    # -- Initiator internals ---------------------------------------------------

    def _close_initiators(self) -> None:
        """Reject new initiator boundaries while inherited continuations drain."""
        if self._initiator_state == "active":
            self._initiator_state = "closing"

    async def _dispose_initiators(self) -> None:
        """Wait for returned-Promise boundaries, then invalidate retained references."""
        if self._initiator_disposal is not None:
            await self._initiator_disposal
            return

        async def _do_dispose() -> None:
            self._close_initiators()
            self._release_reentrant_initiator_runs()
            if self._active_initiator_runs != 0:
                loop = asyncio.get_running_loop()
                self._initiator_drain = loop.create_future()
                await self._initiator_drain
            self._initiator_state = "disposed"

        self._initiator_disposal = asyncio.ensure_future(_do_dispose())
        await self._initiator_disposal

    def _run_with_initiator(self, agent: Agent | None, operation: Callable[[], T]) -> T:
        """Establish one tracked initiator or clearing boundary."""
        if self._initiator_state != "active":
            raise RuntimeError(_DISPOSED_INITIATOR_MESSAGE)

        run = _InitiatorRun(
            active=True,
            parent=self._initiator_run_var.get(),
        )
        self._active_initiator_runs += 1

        token_initiator = self._initiator_var.set(agent)
        token_run = self._initiator_run_var.set(run)
        try:
            result = operation()
        except BaseException:
            self._release_initiator_run(run)
            self._initiator_var.reset(token_initiator)
            self._initiator_run_var.reset(token_run)
            raise

        if inspect.isawaitable(result):
            # Wrap the awaitable to release the run on completion
            async def _tracked() -> T:
                try:
                    return await result  # type: ignore[misc]
                finally:
                    self._release_initiator_run(run)
                    self._initiator_var.reset(token_initiator)
                    self._initiator_run_var.reset(token_run)

            return _tracked()  # type: ignore[return-value]
        else:
            self._release_initiator_run(run)
            self._initiator_var.reset(token_initiator)
            self._initiator_run_var.reset(token_run)
            return result

    def _release_reentrant_initiator_runs(self) -> None:
        """Exclude the boundary chain that initiated this teardown from its own drain."""
        run = self._initiator_run_var.get()
        while run is not None:
            self._release_initiator_run(run)
            run = run.parent

    def _release_initiator_run(self, run: _InitiatorRun) -> None:
        if not run.active:
            return
        run.active = False
        self._active_initiator_runs -= 1
        if self._active_initiator_runs != 0:
            return
        if self._initiator_drain is not None and not self._initiator_drain.done():
            self._initiator_drain.set_result(None)
            self._initiator_drain = None

    def _assert_initiators_readable(self) -> None:
        if self._initiator_state == "disposed":
            raise RuntimeError(_DISPOSED_INITIATOR_MESSAGE)
