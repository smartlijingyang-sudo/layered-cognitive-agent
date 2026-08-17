"""1:1 port of ``@deepseek-ai/dsh-agent/dispatch.ts``.

Agent-scoped dispatch and prompt assembly helpers.  The fused dispatcher
:func:`agent_events` couples the agent subject to its scope carrier, so the
scope key and the payload's ``agent`` cannot diverge; repeat dispatchers (the
loop driver) build it once in the agent's constructor and reuse it.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import Any, Protocol

from lca.layer0_infra.dsh_core.agent.runtime_types import Agent
from lca.layer0_infra.dsh_core.scope import scope_target

# ---------------------------------------------------------------------------
# AssembleContext — prompt assembly context with agent + scope
# ---------------------------------------------------------------------------


@dataclass
class AssembleContext:
    """Context passed to prompt assembly.

    The ``agent`` field identifies the agent being assembled for (absent on
    diagnostics).  The ``scope`` is the agent itself as a scope carrier,
    ensuring agent-scoped prompt and tool contributions are visible.
    ``signal`` is the current turn's cancellation signal when assembly
    belongs to a turn.
    """

    agent: Any = None
    scope: Any = None
    signal: Any = None
    variables: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# AgentEventDispatch
# ---------------------------------------------------------------------------


class AgentEventDispatch(Protocol):
    """The fused dispatcher :func:`agent_events` returns.

    Each method dispatches the named agent-subject event with the agent's
    scope carrier as ``thisArg`` and the agent itself injected into the payload.
    """

    def emit(self, name: str, payload: dict[str, Any]) -> None:
        """Fire-and-forget notification in the agent's scope.

        Every listener is invoked; synchronous throws and returned-promise
        rejections are logged and contained per listener, so a notification
        cannot veto lifecycle progress or starve a later observer.
        """
        ...

    async def serial(self, name: str, payload: dict[str, Any]) -> Any:
        """Awaited in-order dispatch (Cordis ``serial``) in the agent's scope."""
        ...

    async def waterfall(self, name: str, payload: dict[str, Any], *rest: Any) -> Any:
        """Around-middleware dispatch (Cordis ``waterfall``) in the agent's scope."""
        ...


# ---------------------------------------------------------------------------
# agent_carrier
# ---------------------------------------------------------------------------


def agent_carrier(agent: Agent) -> Any:
    """Build the fused scope carrier for one agent subject.

    The carrier is a stateless routing object.  :func:`agent_events` accepts an
    existing carrier, so callers that dispatch repeatedly for the same agent
    (the loop driver) build it once in the agent's constructor and reuse it,
    keeping hot-path dispatches allocation-free.
    """
    return scope_target(agent, agent)


# ---------------------------------------------------------------------------
# agent_events
# ---------------------------------------------------------------------------


def agent_events(
    ctx: Any,
    agent: Agent,
    carrier: Any | None = None,
) -> AgentEventDispatch:
    """Build a dispatcher that couples the agent subject to its scope carrier.

    Args:
        ctx: The context to dispatch through (any context of the app).
        agent: The subject agent; also the scope-carrier key.
        carrier: The scope carrier to dispatch through; defaults to
            :func:`agent_carrier` for the agent.  Pass a constructor-built
            carrier to avoid rebuilding it for every dispatch.

    Returns:
        The fused dispatcher.
    """
    if carrier is None:
        carrier = agent_carrier(agent)

    def fused(payload: dict[str, Any]) -> dict[str, Any]:
        """Inject the agent into the payload so subject and scope key cannot diverge."""
        return {**payload, "agent": agent}

    class _Dispatch:
        def emit(self, name: str, payload: dict[str, Any]) -> None:
            full_payload = fused(payload)
            args = [carrier, name, full_payload]
            # Cordis emit: get filtered callbacks and invoke each, containing errors.
            events = getattr(ctx, "_host", None)
            if events is not None:
                event_bus = getattr(events, "events", None)
                if event_bus is not None and hasattr(event_bus, "dispatch"):
                    callbacks = event_bus.dispatch("emit", args)
                    for callback in callbacks:
                        try:
                            returned = callback(*args)
                            # Fire-and-forget: contain async rejections
                            if hasattr(returned, "__await__"):

                                async def _catch(
                                    err_future: Any = returned,
                                    event_name: str = name,
                                ) -> None:
                                    try:
                                        await err_future
                                    except Exception as exc:
                                        logger = getattr(ctx, "logger", None)
                                        if logger is not None:
                                            with contextlib.suppress(Exception):
                                                logger.warning(
                                                    'agent event "%s" listener rejected: %s',
                                                    event_name,
                                                    exc,
                                                )

                                task = asyncio.ensure_future(_catch())
                                task.add_done_callback(_discard)
                        except Exception as exc:
                            logger = getattr(ctx, "logger", None)
                            if logger is not None:
                                with contextlib.suppress(Exception):
                                    logger.warning(
                                        'agent event "%s" listener threw: %s',
                                        name,
                                        exc,
                                    )
                    return

            # Fallback: use ctx.emit if direct dispatch not available
            with contextlib.suppress(RuntimeError):
                loop = asyncio.get_running_loop()
                task = loop.create_task(ctx.emit(name, full_payload))
                task.add_done_callback(_discard)

        async def serial(self, name: str, payload: dict[str, Any]) -> Any:
            full_payload = fused(payload)
            return await ctx.serial(name, carrier, full_payload)

        async def waterfall(self, name: str, payload: dict[str, Any], *rest: Any) -> Any:
            full_payload = fused(payload)
            return await ctx.waterfall(name, carrier, full_payload, *rest)

    return _Dispatch()


def _discard(_task: Any) -> None:
    """Swallow done-callback exceptions from fire-and-forget tasks."""


# ---------------------------------------------------------------------------
# emit_agent_event
# ---------------------------------------------------------------------------


def emit_agent_event(
    ctx: Any,
    agent: Agent,
    name: str,
    payload: dict[str, Any],
) -> None:
    """Emit one contained agent notification without allocating a retained dispatcher.

    Args:
        ctx: The context to dispatch through.
        agent: The subject agent and scope key.
        name: The agent-subject event to emit.
        payload: The event's payload fields; ``agent`` is injected.
    """
    agent_events(ctx, agent).emit(name, payload)


# ---------------------------------------------------------------------------
# assemble_context_for
# ---------------------------------------------------------------------------


def assemble_context_for(agent: Agent, signal: Any = None) -> AssembleContext:
    """Build the prompt assembly context with agent and scope set together.

    Agent-scoped prompt and tool contributions cannot be silently omitted.

    Args:
        agent: The agent the assembly is for.
        signal: The current turn's explicit control signal, when assembly
            belongs to a turn.

    Returns:
        The context to pass to ``assemble()``.
    """
    return AssembleContext(
        agent=agent,
        scope=agent,
        signal=signal,
    )
