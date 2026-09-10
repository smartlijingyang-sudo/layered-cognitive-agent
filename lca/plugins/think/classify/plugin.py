"""phase.think.classify — convert LLMResponse to Decision via DecisionClassifier.

ADR-0217 §3.3:本 plugin 实现 NodeExecutor 协议(think 子图专用),同时保留
@plugin(...) 装饰器注册(Cordis 容器兼容)。双注册互不替代。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

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
from lca.contracts.plugins.think.step_plugin_spec import step_plugin_spec
from lca.contracts.models.core.execution.think_carry import CARRY_KEY, ThinkSubgraphCarry
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseContext,
    PhaseInput,
    PhaseResult,
)
from lca.contracts.protocols.declarative.declarative_1.factory_resolver import (
    get_default_registry,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.gate.decision_classifier import DecisionClassifier
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.loop.phase._shared.common import StandardPhaseConfig

_SEMANTIC_NAME = "think.classify"
_REGION = "phase:think"

STAGE_KIND = "think_stage"

SPEC = step_plugin_spec(
    plugin_id="phase.think.classify",
    module="lca.plugins.think.classify.plugin",
    test_suite="tests/think/test_classify_phase_plugin.py",
)


def _carry(context: PhaseContext) -> ThinkSubgraphCarry:
    existing = context.artifacts.get(CARRY_KEY)
    if isinstance(existing, ThinkSubgraphCarry):
        return existing
    return ThinkSubgraphCarry(state=context.state)


@dataclass(frozen=True, slots=True)
class ThinkClassifyExecutor:
    """think 节点:把 LLMResponse 通过 DecisionClassifier 转 Decision。"""

    semantic_name: str = _SEMANTIC_NAME

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        # 老 PhaseExecutor 路径(保留 carry 语义,兼容 tests + 老 caller)
        carry = _carry(context)
        if carry.response is None:
            return PhaseResult(result_kind=STAGE_KIND, payload=carry)
        classifier = context.capabilities.get("phase.think.classify")
        if classifier is None:
            return PhaseResult(result_kind=STAGE_KIND, payload=carry)
        assert isinstance(classifier, DecisionClassifier), (  # noqa: S101
            "phase.think.classify must implement DecisionClassifier"
        )
        decision = classifier.classify(carry.response)
        return PhaseResult(
            result_kind=STAGE_KIND,
            payload=replace(carry, decision=decision),
        )

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """think 子图节点入口。

        inputs 端口(yaml):response
        outputs 端口(yaml):decision
        """
        runtime = context.runtime
        classifier = runtime.get("decision_classifier") if isinstance(runtime, dict) else None
        response = input.port_values.get("response")

        if classifier is None or response is None:
            return NodeOutput(port_values={})

        assert isinstance(classifier, DecisionClassifier), (  # noqa: S101
            "think.classify runtime['decision_classifier'] must implement DecisionClassifier"
        )
        decision = classifier.classify(response)
        return NodeOutput(port_values={"decision": decision})


@plugin(
    id="phase.think.classify",
    Config=StandardPhaseConfig,
    provides=("phase.think.classify",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/think/test_classify_phase_plugin.py",
    spec=SPEC,
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
                "phase_think_classify.checked",
                "phase_think_classify.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: StandardPhaseConfig) -> None:
    """双注册:cordis provide + FactoryRegistry register。"""
    del config
    executor = ThinkClassifyExecutor()
    ctx.provide("phase.think.classify", executor)
    get_default_registry().register(
        executor,
        semantic_name=_SEMANTIC_NAME,
        region=_REGION,
    )


def create_executor() -> ThinkClassifyExecutor:
    return ThinkClassifyExecutor()


__all__ = ["ThinkClassifyExecutor", "create_executor", "setup"]
