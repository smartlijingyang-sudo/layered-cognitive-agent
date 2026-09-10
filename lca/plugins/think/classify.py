"""phase.think.classify — convert LLMResponse to Decision via DecisionClassifier.

think 子图节点 plugin:把 LLMResponse 转换为 Decision。
``requires=("decision_classifier",)`` 通过 Cordis 校验,
运行时从 ``context.runtime.decision_classifier`` 拿 capability 实例。

ADR-0218 §3.3:节点 plugin 由作者显式书写完整 ``@plugin(...)`` 装饰器,
工厂 ``setup(ctx)`` 通过 Cordis ``ctx.provide`` 双键注册
(composite + region-less,think 子图专用的 NodeExecutor 解析)。
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
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.gate.decision_classifier import DecisionClassifier
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class ThinkClassifyExecutor:
    """think 节点:把 LLMResponse 通过 DecisionClassifier 转 Decision。"""

    semantic_name: str = "think.classify"
    region: str = "phase:think"
    # ADR-0219 §5.5: typed port contract declared on the plugin (graph
    # layer does not know port names; it only knows topology).
    declared_inputs: tuple[PortName, ...] = ("response",)
    declared_outputs: tuple[PortName, ...] = ("decision",)

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
        classifier = runtime.decision_classifier
        response = input.port_values.get("response")

        if classifier is None or response is None:
            return NodeOutput(port_values={})

        assert isinstance(classifier, DecisionClassifier), (  # noqa: S101
            "think.classify runtime.decision_classifier must implement DecisionClassifier"
        )
        decision = classifier.classify(response)
        return NodeOutput(port_values={"decision": decision})


@plugin(
    id="phase.think.classify",
    Config=None,
    provides=("phase:think::think.classify",),
    requires=("decision_classifier",),
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
                "phase_think_classify.checked",
                "phase_think_classify.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve", "decision_classifier"),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Composite-key registration: ``{region}::{semantic_name}``."""
    del config
    executor = ThinkClassifyExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ThinkClassifyExecutor", "setup"]
