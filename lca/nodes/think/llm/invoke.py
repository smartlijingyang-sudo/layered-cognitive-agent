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
    declared_inputs: tuple[PortName, ...] = ("model_visible_request", "adapter")
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
        """
        del context
        request = _resolve_port("model_visible_request", input=input)
        adapter = _resolve_port("adapter", input=input)

        prompt = request.messages[-1]["content"] if request.messages else ""
        history = request.messages[:-1] if len(request.messages) > 1 else []

        response: LLMResponse = LLMResponse(text="")
        async for event in adapter.stream(
            prompt,
            system=request.system,
            history=history,
            tools=list(request.tools) if request.tools else None,
        ):
            if event.type is LLMStreamEventType.COMPLETED and event.response is not None:
                response = event.response

        return NodeOutput(
            port_values={
                "llm_response": response,
                "usage": response.usage or TokenUsage(),
            }
        )


def _resolve_port(name: str, *, input: NodeInput) -> Any:
    """Read a typed-only port from ``input.port_values``.

    Invoke is a pure typed-port node: it never reads from
    ``context.runtime``. The journal write path (``writer`` / ``step``)
    belongs to the sibling ``think.llm.persist`` node.
    """
    value = input.port_values.get(name)
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
