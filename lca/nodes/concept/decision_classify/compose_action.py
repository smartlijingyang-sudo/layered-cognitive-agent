"""phase.concept.decision_classify.decision_compose_action — typed Decision composer.

concept.decision.classify 图节点 3:typed ``tuple[ToolCall, ...]`` +
``tuple[DelegationSpec, ...]`` + ``str`` → ``Decision`` typed boundary
(ADR-0220 §4.1 + §3.3)。

节点职责:在 delegations / tool_calls / intent 三路输入上做优先级合成
(DELEGATE > USE_TOOL > RESPOND),产出 typed ``Decision``。空输入 →
``action_type=RESPOND`` + 模型空响应提示(对齐 ``DefaultDecisionClassifier``
语义,保证业务路径不退化)。
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.enums.enums import ActionType
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
from lca.contracts.models.core.execution.decision import Decision, DelegationSpec, ToolCall
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

_PARSE_FAILURE_USER_MESSAGE = "抱歉，模型未返回有效决策，请重试。"


@dataclass(frozen=True, slots=True)
class DecisionComposeActionExecutor:
    """concept.decision.classify 节点 3:tool_calls + delegations + intent → Decision。"""

    semantic_name: str = "decision.compose.action"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("tool_calls", "delegations", "intent")
    declared_outputs: tuple[PortName, ...] = ("decision",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """decision.compose.action 入口。

        inputs 端口(yaml):tool_calls (tuple[ToolCall, ...]),
        delegations (tuple[DelegationSpec, ...]), intent (str)
        outputs 端口(yaml):decision (Decision)
        """
        del context
        tool_calls = input.port_values.get("tool_calls") or ()
        delegations = input.port_values.get("delegations") or ()
        intent = input.port_values.get("intent") or ""

        if not isinstance(tool_calls, tuple):
            raise TypeError(
                "decision.compose.action: 'tool_calls' port must be a tuple, "
                f"got {type(tool_calls).__name__}"
            )
        if not isinstance(delegations, tuple):
            raise TypeError(
                "decision.compose.action: 'delegations' port must be a tuple, "
                f"got {type(delegations).__name__}"
            )
        if not isinstance(intent, str):
            raise TypeError(
                f"decision.compose.action: 'intent' port must be str, got {type(intent).__name__}"
            )

        decision = _compose(tool_calls=tool_calls, delegations=delegations, intent=intent)
        return NodeOutput(port_values={"decision": decision})


def _compose(
    *,
    tool_calls: tuple[ToolCall, ...],
    delegations: tuple[DelegationSpec, ...],
    intent: str,
) -> Decision:
    """Branch on the typed inputs to produce one Decision.

    Priority: DELEGATE > USE_TOOL > RESPOND. Empty intent + empty calls
    + empty delegations → RESPOND with the parse-failure user message
    (matches ``DefaultDecisionClassifier.classify`` empty-response branch).
    """
    if delegations:
        return Decision(
            decision_id=new_id("dec"),
            action_type=ActionType.DELEGATE.value,
            rationale="",
            confidence=1.0,
            delegations=list(delegations),
        )
    if tool_calls:
        return Decision(
            decision_id=new_id("dec"),
            action_type=ActionType.USE_TOOL.value,
            rationale="",
            confidence=1.0,
            tool_calls=list(tool_calls),
        )
    if intent:
        return Decision(
            decision_id=new_id("dec"),
            action_type=ActionType.RESPOND.value,
            rationale="",
            confidence=1.0,
            response_text=intent,
        )
    return Decision(
        decision_id=new_id("dec"),
        action_type=ActionType.RESPOND.value,
        rationale="模型返回空响应",
        confidence=0.0,
        response_text=_PARSE_FAILURE_USER_MESSAGE,
    )


@plugin(
    id="phase.concept.decision_classify.decision_compose_action",
    Config=None,
    provides=("concept::decision.compose.action",),
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
                "phase_concept_decision_classify_decision_compose_action.checked",
                "phase_concept_decision_classify_decision_compose_action.served",
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
    executor = DecisionComposeActionExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["DecisionComposeActionExecutor", "_compose", "setup"]
