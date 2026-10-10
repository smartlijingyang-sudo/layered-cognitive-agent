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

The native-call → ``ToolCall`` projection is shared with
``decision_classify.decision.parse.response`` via
:func:`lca.cognition.brain.llm_turn.response_projection.project_llm_response`;
this node emits a single :class:`Decision` (the spec §E node emits
``decision`` as one typed port, not the typed-port split used by
``concept.decision.classify``).

Canonical shape: hand-written ``@dataclass(frozen=True, slots=True)`` +
``@plugin(...)`` carrier, per ADR-0228 D2.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lca.cognition.brain.llm_turn.response_projection import project_llm_response
from lca.cognition.memory.acknowledgement import guard_reply
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
from lca.contracts.models.cognition.prompt_leak_markers import LEAK_MARKER_PATTERNS
from lca.contracts.models.core.execution.decision import (
    Decision,
    DelegationSpec,
    ToolCall,
    requires_human_input,
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
from lca.nodes._resolve import resolve_typed_port_or_runtime

if TYPE_CHECKING:
    from lca.contracts.models.core.conversation.llm import LLMResponse


_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DecisionParseExecutor:
    """think.decision.parse 节点:LLMResponse → :class:`Decision`."""

    semantic_name: str = "decision.parse"
    region: str = "think"
    declared_inputs: tuple[PortName, ...] = (PortName("state"), PortName("llm_response"))
    declared_outputs: tuple[PortName, ...] = (PortName("decision"),)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """Project an :class:`LLMResponse` into a :class:`Decision`."""
        resolve_typed_port_or_runtime(
            PortName("state"), input=input, context=context, node="decision.parse"
        )
        llm_response = resolve_typed_port_or_runtime(
            PortName("llm_response"), input=input, context=context, node="decision.parse"
        )
        tool_calls, delegations, intent = _project_response(llm_response)
        action_type = _infer_action_type(tool_calls=tool_calls, delegations=delegations)
        decision_id = new_id("decision")
        clean_intent = _guard_prompt_leak(intent) or ""
        response_text = clean_intent if action_type == "respond" else None
        response_text = _guard_acknowledgement(context=context, text=response_text)
        return NodeOutput(
            port_values={
                PortName("decision"): Decision(
                    decision_id=decision_id,
                    action_type=action_type,
                    rationale=clean_intent,
                    confidence=1.0,
                    tool_calls=list(tool_calls),
                    delegations=list(delegations),
                    response_text=response_text,
                    needs_approval=requires_human_input(tool_calls),
                )
            }
        )


# RA-116: the cutoff pattern is built from the canonical marker seam
# (lca.contracts.models.cognition.prompt_leak_markers). The three dead
# markers (## 认知闭集 / ## 核心不变量 / ## 系统指令) were removed:
# grep proved they appear in no prompt-producing code.
_LEAK_CUTOFF_REGEX = re.compile(
    r"(\n*\s*(?:" + "|".join(LEAK_MARKER_PATTERNS) + r").*)$",
    re.DOTALL | re.IGNORECASE,
)

_SAFE_FALLBACK_RESPONSE = "好的，我正在为您处理该请求，请稍候。"


def _guard_prompt_leak(text: str | None) -> str | None:
    """Guard against model regurgitating internal prompt directives.

    Strips leaked trailing instructions (Deferred tool namespaces, 记忆写入与写盘铁律, etc.)
    and replaces pure-leak regurgitation with a polite fallback message.
    """
    if not text:
        return text

    # Strip any trailing leaked prompt block
    cleaned = _LEAK_CUTOFF_REGEX.sub("", text).strip()
    if cleaned:
        return cleaned

    # If nothing remains after stripping the leaked section, check if leak was present
    if _LEAK_CUTOFF_REGEX.search(text):
        return _SAFE_FALLBACK_RESPONSE

    return text


def _guard_acknowledgement(*, context: NodeContext, text: str | None) -> str | None:
    """Allow a user-visible "remembered" claim only from an unspent successful write.

    Assistant memory holds one unspent successful projection at a time. A
    claiming reply spends it; a non-claiming reply does not. With no assistant
    memory and no injected receipt a claiming reply is replaced by the refusal
    (ADR-0260 S6 fail-closed). An injected receipt still follows
    ``may_acknowledge`` and is not spent.
    """
    return guard_reply(text, getattr(context, "runtime", None))


def _project_response(
    response: LLMResponse,
) -> tuple[list[ToolCall], list[DelegationSpec], str]:
    """Split native tool calls + delegations and recover leaked JSON from text."""
    projected = project_llm_response(response)
    return list(projected.tool_calls), list(projected.delegations), projected.intent


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
