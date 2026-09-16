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
    declared_inputs: tuple[PortName, ...] = ("state", "model_visible_request", "adapter")
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
        last message becomes the prompt, prior messages become history.

        ``state`` (kernel-injected carrier) and the ``cursor`` /
        ``reasoner_prompt`` identity are forwarded to the streaming
        boundary: ``ModelVisibleHookAdapter`` needs them to publish
        ``llm.request.header`` — the single fact that opens a journal
        step — and streaming is what emits ``llm.stream.token``. A
        non-streaming or identity-less call leaves ``journal.steps``
        empty (regression guarded by ``test_invoke``).
        """
        state = _resolve_port("state", input=input, context=context)
        request = _resolve_port("model_visible_request", input=input)
        adapter = _resolve_port("adapter", input=input)

        prompt = request.messages[-1]["content"] if request.messages else ""
        history = request.messages[:-1] if len(request.messages) > 1 else []
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


def _resolve_port(name: str, *, input: NodeInput, context: NodeContext | None = None) -> Any:
    """Read a port: typed ``input.port_values`` first, then whitelisted runtime.

    ``state`` is a kernel-injected runtime carrier, so it resolves via
    ``context.runtime`` when not supplied as an explicit typed port. The
    other inputs (``model_visible_request`` / ``adapter``) are typed-only.
    """
    value = input.port_values.get(name)
    if value is None and name == "state" and context is not None:
        runtime = getattr(context, "runtime", None)
        if runtime is not None:
            value = getattr(runtime, name, None)
            if value is None and hasattr(runtime, "get"):
                value = runtime.get(name)
    if value is None:
        raise TypeError(f"llm.invoke: '{name}' port must be supplied via input.port_values")
    return value


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
