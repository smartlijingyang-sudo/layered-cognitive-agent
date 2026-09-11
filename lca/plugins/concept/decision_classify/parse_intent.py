"""phase.concept.decision_classify.decision_parse_intent — typed intent parse.

concept.decision.classify 图节点 2:typed ``LLMResponse`` → ``str``
(ADR-0220 §3.3)。

节点职责:把 ``LLMResponse.text`` 投影成 intent 字符串,这是 RESPOND 决策
的 `response_text` 来源。当 LLM 同时返回 tool_calls + text 时,text
通常被忽略(默认 provider 语义),但本节点纯透传 text 字段 —— 决策
语义由 ``decision.compose.action`` 节点决定 action_type 后再选哪一份
输入。
"""

from __future__ import annotations

from dataclasses import dataclass

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
from lca.contracts.models.core.conversation.llm import LLMResponse
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
class DecisionParseIntentExecutor:
    """concept.decision.classify 节点 2:LLMResponse → str(intent)。"""

    semantic_name: str = "decision.parse.intent"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("response",)
    declared_outputs: tuple[PortName, ...] = ("intent",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """decision.parse.intent 入口。

        inputs 端口(yaml):response (LLMResponse)
        outputs 端口(yaml):intent (str)
        """
        del context
        response = input.port_values.get("response")
        if not isinstance(response, LLMResponse):
            raise TypeError(
                "decision.parse.intent: 'response' port must be an LLMResponse, "
                f"got {type(response).__name__}"
            )
        return NodeOutput(port_values={"intent": (response.text or "").strip()})


@plugin(
    id="phase.concept.decision_classify.decision_parse_intent",
    Config=None,
    provides=("concept::decision.parse.intent",),
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
                "phase_concept_decision_classify_decision_parse_intent.checked",
                "phase_concept_decision_classify_decision_parse_intent.served",
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
    executor = DecisionParseIntentExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["DecisionParseIntentExecutor", "setup"]
