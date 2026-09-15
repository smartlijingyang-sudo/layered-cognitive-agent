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
from lca.contracts.models.core.conversation.llm import (
    LLMResponse,
    LLMStreamEventType,
    TokenUsage,
)
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
        # The adapter contract is ``stream(prompt, system=..., history=..., tools=...)``;
        # the typed ``ModelVisibleRequest`` is the in-process view, not the wire shape.
        # Unpack it here so the node body owns the typed-boundary translation.
        # Streaming, not ``complete``, is the boundary that produces
        # ``llm.stream.token``: the reasoning channel is what the journal folds
        # ``thinking.reasoning`` from, and a non-streaming call discards it.
        prompt = request.messages[-1]["content"] if request.messages else ""
        history = request.messages[:-1] if len(request.messages) > 1 else []
        # FactGateway resolves the bound publish seam for llm.call.start/end and
        # step.tool_call.record; injecting a Session here would route the append
        # around the run bridge and lose the ledger write.
        #
        # ``cursor`` + ``reasoner_prompt`` are the model-visible identity the
        # outer adapter needs to publish ``llm.request.header`` — the single
        # fact that opens a journal step. Same explicit DI as
        # ``lca.plugins.primitive.llm_call.invoke``.
        cursor, reasoner_prompt = _model_visible_identity(state, request)
        response: LLMResponse = LLMResponse(text="")
        async for event in adapter.stream(
            prompt,
            system=request.system,
            history=history,
            tools=list(request.tools) if request.tools else None,
            state=state,
            turn=int(state.extra.get("current_turn", 0)),
            step=state.step,
            cursor=cursor,
            reasoner_prompt=reasoner_prompt,
        ):
            if event.type is LLMStreamEventType.COMPLETED and event.response is not None:
                response = event.response
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


def _model_visible_identity(state: Any, request: Any) -> tuple[Any, Any]:
    """Build the ``(cursor, reasoner_prompt)`` pair for the model-visible hook.

    ``cursor`` comes from the per-turn :class:`CursorRecord` binding; without a
    cursor there is no step identity, so the hook stays transparent (same
    degradation as ``primitive.llm.call``).
    """
    from lca.cognition.body.executor.cursor_record import CursorRecord
    from lca.plugins.events.hooks.model_visible.reasoner_prompt import (
        CurrentReasonerPrompt,
    )

    cursor = CursorRecord.get()
    step = int(getattr(state, "step", 0) or 0)
    if cursor is not None:
        step_index = getattr(getattr(cursor, "snapshot", None), "step_index", None)
        if isinstance(step_index, int):
            step = step_index + 1
    reasoner_prompt = CurrentReasonerPrompt(
        step_id=f"step-{step:03d}",
        template_id="",
        selector_decision_path="",
        system_prompt_text=str(request.system or ""),
    )
    return cursor, reasoner_prompt


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
