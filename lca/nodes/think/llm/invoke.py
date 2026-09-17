"""``think.llm.invoke`` graph node (PR-B single-responsibility split).

Single responsibility: drive the LLM adapter once per think turn.

Reads :class:`ModelVisibleRequest` and the bound :class:`LLMAdapter` from
typed ports, collects the streamed :class:`LLMResponse` and
:class:`TokenUsage`, and forwards both as typed outputs. Does NOT write
the journal — that lives in the sibling ``think.llm.persist`` node
(spec §C persist-before-execute split).

Pair shape (PR-B):

- ``think.llm.invoke`` (this node): typed ports → adapter call
- ``think.llm.persist``: response → writer.append_* (journal side-effect)

Canonical shape: hand-written ``@dataclass(frozen=True, slots=True)`` +
``@plugin(...)`` carrier, per ADR-0228 D2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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


@dataclass(frozen=True, slots=True)
class LlmInvokeExecutor:
    """think.llm.invoke 节点: ``ModelVisibleRequest`` → ``(LLMResponse, TokenUsage)``."""

    semantic_name: str = "llm.invoke"
    region: str = "think"
    # Runtime-carrier read for ``state`` + ``adapter`` (the plan validator
    # does not model runtime carriers as port producers, and the rest
    # of the think subgraph uses the same pattern).
    declared_inputs: tuple[PortName, ...] = ("model_visible_request",)
    declared_outputs: tuple[PortName, ...] = ("llm_response", "usage")

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """Stream the adapter with the model-visible slice and return the response.

        The typed ``ModelVisibleRequest`` is the in-process view; the
        adapter wire shape is ``stream(prompt, system=..., history=...,
        tools=...)``. The node owns this typed-boundary translation —
        a trailing user turn becomes the prompt, every other row stays in
        history (see :func:`_split_wire_turn`).

        ``state`` (kernel-injected carrier) and the ``cursor`` /
        ``reasoner_prompt`` identity are forwarded to the streaming
        boundary: ``ModelVisibleHookAdapter`` needs them to publish
        ``llm.request.header`` — the single fact that opens a journal
        step — and streaming is what emits ``llm.stream.token``. A
        non-streaming or identity-less call leaves ``journal.steps``
        empty (regression guarded by ``test_invoke``).
        """
        state = _resolve_state(context=context)
        request = _resolve_port("model_visible_request", input=input)
        adapter = _resolve_adapter(context=context)

        prompt, history = _split_wire_turn(request.messages)
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

        return NodeOutput(
            port_values={
                "llm_response": response,
                "usage": response.usage or TokenUsage(),
            }
        )


def _split_wire_turn(messages: Any) -> tuple[str, list[Any]]:
    """Split the derived message list onto the adapter's ``(prompt, history)`` seam.

    Only a trailing ``role=user`` row with text becomes the prompt. Any
    other trailing row stays in ``history``: the wire builder renders the
    prompt as a *new* user turn, so handing it a ``role=tool`` row would
    strip that row's ``tool_call_id`` and leave the assistant's
    ``tool_calls`` unanswered, and handing it a ``role=assistant`` row
    would drop the declared calls outright.
    """
    rows: list[Any] = list(messages or ())
    if rows:
        last = rows[-1]
        content = last.get("content") if isinstance(last, dict) else None
        if (
            isinstance(last, dict)
            and last.get("role") == "user"
            and isinstance(content, str)
            and content.strip()
        ):
            return content, rows[:-1]
    return "", rows


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


def _resolve_port(name: str, *, input: NodeInput) -> Any:
    """Read a typed port from ``input.port_values``.

    Typed-port-only read. Runtime-carrier resources (e.g. ``state``)
    use :func:`_resolve_state` instead so the plan validator sees an
    empty ``declared_inputs`` set and the kernel-carrier flow remains
    unimpeded.
    """
    value = input.port_values.get(name)
    if value is None:
        raise TypeError(f"llm.invoke: '{name}' port must be supplied via input.port_values")
    return value


def _resolve_state(*, context: NodeContext) -> Any:
    """Pull ``state`` from the whitelisted kernel runtime carrier."""
    runtime = getattr(context, "runtime", None)
    state_obj = getattr(runtime, "state", None) if runtime is not None else None
    if state_obj is None and runtime is not None and hasattr(runtime, "get"):
        state_obj = runtime.get("state")
    if state_obj is None:
        raise TypeError("llm.invoke: 'state' must be supplied via context.runtime")
    return state_obj


def _resolve_adapter(*, context: NodeContext) -> Any:
    """Pull the LLMAdapter from the runtime carrier (``adapter`` key)."""
    runtime = getattr(context, "runtime", None)
    adapter = getattr(runtime, "adapter", None) if runtime is not None else None
    if adapter is None and runtime is not None and hasattr(runtime, "get"):
        adapter = runtime.get("adapter")
    if adapter is None:
        raise TypeError("llm.invoke: 'adapter' must be supplied via context.runtime")
    return adapter


@plugin(
    id="phase.think.llm.invoke",
    Config=None,
    provides=("think::llm.invoke",),
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
                "phase_think_llm_invoke.checked",
                "phase_think_llm_invoke.served",
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
    """Composite-key 注册: ``{region}::{semantic_name}``。"""
    del config
    executor = LlmInvokeExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["LlmInvokeExecutor", "setup"]
