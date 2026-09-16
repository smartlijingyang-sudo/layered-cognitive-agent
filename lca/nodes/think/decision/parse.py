"""``think.decision.parse`` graph node (spec §E).

Single responsibility: project an :class:`LLMResponse` into a typed
:class:`Decision` for downstream ``think.gate`` (and the outer
interpreter).

This is the third of three single-responsibility nodes that replace
``think.reason.complete``:

- ``think.history.assemble`` (Task 2): writer → :class:`ModelVisibleRequest`
- ``think.llm.dispatch`` (Task 3): LLM call → :class:`LLMResponse`
- ``think.decision.parse`` (Task 3): :class:`LLMResponse` → :class:`Decision`

The orchestrator ``think.reason`` wires them via edges; the deleted
``complete`` node used to do all three jobs inline.

The parse mirrors ``decision_classify.decision.parse.response`` but emits
a single :class:`Decision` (the spec §E node emits ``decision`` as one
typed port, not the typed-port split used by ``concept.decision.classify``).

Canonical shape: hand-written ``@dataclass(frozen=True, slots=True)`` +
``@plugin(...)`` carrier, per ADR-0228 D2.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.execution.decision import (
    Decision,
    DelegationSpec,
    ToolCall,
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

if TYPE_CHECKING:
    from lca.contracts.models.core.conversation.llm import LLMResponse


_log = logging.getLogger(__name__)

_DELEGATE_TOOL_NAME = "delegate"


@dataclass(frozen=True, slots=True)
class DecisionParseExecutor:
    """think.decision.parse 节点:LLMResponse → :class:`Decision`."""

    semantic_name: str = "decision.parse"
    region: str = "think"
    declared_inputs: tuple[PortName, ...] = ("state", "llm_response")
    declared_outputs: tuple[PortName, ...] = ("decision",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """Project an :class:`LLMResponse` into a :class:`Decision`."""
        _resolve_port("state", input=input, context=context)
        llm_response = _resolve_port("llm_response", input=input, context=context)
        tool_calls, delegations, intent = _project_response(llm_response)
        action_type = _infer_action_type(tool_calls=tool_calls, delegations=delegations)
        decision_id = new_id("decision")
        return NodeOutput(
            port_values={
                "decision": Decision(
                    decision_id=decision_id,
                    action_type=action_type,
                    rationale=intent,
                    confidence=1.0,
                    tool_calls=list(tool_calls),
                    delegations=list(delegations),
                    response_text=intent if action_type == "respond" else None,
                )
            }
        )


def _resolve_port(
    name: str, *, input: NodeInput, context: NodeContext
) -> Any:
    """Read a declared port from ``input.port_values`` or ``context.runtime``."""
    value = input.port_values.get(name)
    if value is None and hasattr(context, "runtime") and context.runtime is not None:
        value = getattr(context.runtime, name, None)
        if value is None and hasattr(context.runtime, "get"):
            value = context.runtime.get(name)
    if value is None:
        raise TypeError(
            f"decision.parse: '{name}' port must be supplied via input.port_values or context.runtime"
        )
    return value


def _project_response(
    response: LLMResponse,
) -> tuple[list[ToolCall], list[DelegationSpec], str]:
    """Split native tool calls + delegations and recover leaked JSON from text."""
    from lca.cognition.brain.prompt.leaked_tool_call import (
        recover_leaked_tool_calls,
    )

    leftover = (response.text or "").strip()
    native_calls = list(response.tool_calls or ())
    if not native_calls and leftover:
        leftover, recovered = recover_leaked_tool_calls(leftover)
        native_calls = recovered

    delegations: list[DelegationSpec] = []
    tool_calls: list[ToolCall] = []
    for tc in native_calls:
        if tc.name == _DELEGATE_TOOL_NAME:
            delegations.append(
                DelegationSpec(
                    subtask=str(tc.arguments.get("subtask", "")),
                    target_role=tc.arguments.get("target_role") or None,
                    target_agent_id=tc.arguments.get("target_agent_id") or None,
                )
            )
            continue
        tool_calls.append(
            ToolCall(
                call_id=tc.call_id or new_id("call"),
                tool_name=tc.name,
                arguments=dict(tc.arguments),
            )
        )
    return tool_calls, delegations, leftover


def _infer_action_type(
    *,
    tool_calls: list[ToolCall],
    delegations: list[DelegationSpec],
) -> str:
    """Pick the :class:`Decision.action_type` from the parsed payload."""
    if delegations:
        return "delegate"
    if tool_calls:
        return "use_tool"
    return "respond"


@plugin(
    id="phase.think.decision.parse",
    Config=None,
    provides=("think::decision.parse",),
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
                "phase_think_decision_parse.checked",
                "phase_think_decision_parse.served",
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
    executor = DecisionParseExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["DecisionParseExecutor", "setup"]
