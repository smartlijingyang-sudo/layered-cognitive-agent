"""``think.llm.dispatch`` graph node (spec §E, ADR-0226 §4).

Single responsibility: invoke the LLM adapter once per think turn, persist
the assistant message + tool calls to the Session via
:class:`RunSessionWriter` BEFORE any tool execution (persist-before-execute
invariant, spec §C), and emit the ``LLMResponse`` + ``TokenUsage`` to the
downstream ``think.decision.parse`` node.

This is one of three single-responsibility nodes that replace the
retired ``think.reason.complete``:

- ``think.history.assemble`` (Task 2): writer → :class:`ModelVisibleRequest`
- ``think.llm.dispatch`` (Task 3): :class:`ModelVisibleRequest` → LLM call,
  journal ``surface/assistant_message`` + ``log/tool_call`` rows
- ``think.decision.parse`` (Task 3): :class:`LLMResponse` → :class:`Decision`

The orchestrator ``think.reason`` wires them via edges; the deleted
``complete`` node used to do all three jobs inline.

Canonical shape: hand-written ``@dataclass(frozen=True, slots=True)`` +
``@plugin(...)`` carrier, per ADR-0228 D2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.cognition.body.emit._args_summary import summarize_args
from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.conversation.llm import LLMResponse, TokenUsage
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.session.bindings import resolve_session_reader
from lca.loop.commit.tool_journal import record_step_tool_call


@dataclass(frozen=True, slots=True)
class LlmCallExecutor:
    """think.llm.dispatch 节点:ModelVisibleRequest → (LLMResponse, TokenUsage)."""

    semantic_name: str = "llm.call"
    region: str = "phase:think"
    declared_inputs: tuple[PortName, ...] = (
        "state",
        "writer",
        "model_visible_request",
        "adapter",
    )
    declared_outputs: tuple[PortName, ...] = ("llm_response", "usage")

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """Call the LLM adapter with the request and persist the result."""
        state = _resolve_port("state", input=input, context=context)
        writer = _resolve_port("writer", input=input, context=context)
        request = _resolve_port("model_visible_request", input=input, context=context)
        adapter = _resolve_port("adapter", input=input, context=context)
        # The adapter contract is ``complete(prompt: str, system=..., history=..., tools=...)``;
        # the typed ``ModelVisibleRequest`` is the in-process view, not the wire shape.
        # Unpack it here so the node body owns the typed-boundary translation.
        prompt = request.messages[-1]["content"] if request.messages else ""
        history = request.messages[:-1] if len(request.messages) > 1 else []
        # session-bound so TelemetryLLMAdapter can route llm.call.start/end through
        # publish_ep_bound with state+session instead of dropping events on the unbound path.
        session = _resolve_session(context)
        response: LLMResponse = await adapter.complete(
            prompt,
            system=request.system,
            history=history,
            tools=list(request.tools) if request.tools else None,
            state=state,
            turn=int(state.extra.get("current_turn", 0)),
            step=state.step,
            session=session,
        )
        usage: TokenUsage | None = response.usage
        tool_calls = list(response.tool_calls or ())
        step = state.step
        for tc in tool_calls:
            arguments = tc.arguments
            record_step_tool_call(
                tool_name=tc.name,
                invocation_id=tc.call_id,
                arguments=arguments,
                arguments_summary=summarize_args(arguments),
                state=state,
                session=session,
            )
        writer.append_assistant_message(
            turn=step,
            step=step,
            role="assistant",
            content=response.text,
            tool_calls=[
                {
                    "id": tc.call_id,
                    "name": tc.name,
                    "arguments": tc.arguments,
                }
                for tc in tool_calls
            ]
            or None,
            usage=usage,
        )
        for tc in tool_calls:
            writer.append_tool_call(
                turn=step,
                step=step,
                call_id=tc.call_id,
                name=tc.name,
                arguments=str(tc.arguments),
            )
        return NodeOutput(
            port_values={
                "llm_response": response,
                "usage": usage or TokenUsage(),
            }
        )


def _resolve_port(name: str, *, input: NodeInput, context: NodeContext) -> Any:
    """Read a declared port from ``input.port_values`` or ``context.runtime``."""
    value = input.port_values.get(name)
    if value is None and hasattr(context, "runtime") and context.runtime is not None:
        value = getattr(context.runtime, name, None)
        if value is None and hasattr(context.runtime, "get"):
            value = context.runtime.get(name)
    if value is None:
        raise TypeError(
            f"llm.call: '{name}' port must be supplied via input.port_values or context.runtime"
        )
    return value


def _resolve_session(context: NodeContext) -> Any:
    """Prefer ``context.runtime.session``; fall back to module-level binding.

    ``TelemetryLLMAdapter.complete`` emits ``llm.call.start/end`` via
    ``publish_ep_bound``, which drops events when both ``session`` and the
    module-level ``_ACTIVE_SESSION`` are unbound.
    """
    runtime = getattr(context, "runtime", None)
    if runtime is not None:
        session = getattr(runtime, "session", None)
        if session is None and hasattr(runtime, "get"):
            session = runtime.get("session")
        if session is not None:
            return session
    return resolve_session_reader()


@plugin(
    id="phase.think.llm.call",
    Config=None,
    provides=("phase:think::llm.call",),
    requires=(),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_think_llm_call.checked",
                "phase_think_llm_call.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Composite-key 注册:``{region}::{semantic_name}``。"""
    del config
    executor = LlmCallExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["LlmCallExecutor", "setup"]
