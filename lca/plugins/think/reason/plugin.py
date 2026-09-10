"""phase.think.reason — call the LLM via Reasoner, emitting spine facts.

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
from lca.contracts.protocols import Reasoner
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
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.loop.emit.cognitive.reasoner import run_reasoner_with_spine_facts
from lca.plugins.loop.phase._shared.common import StandardPhaseConfig

_SEMANTIC_NAME = "think.reason"
_REGION = "phase:think"

STAGE_KIND = "think_stage"

SPEC = step_plugin_spec(
    plugin_id="phase.think.reason",
    module="lca.plugins.think.reason.plugin",
    test_suite="tests/think/test_reason_phase_plugin.py",
)


def _carry(context: PhaseContext) -> ThinkSubgraphCarry:
    existing = context.artifacts.get(CARRY_KEY)
    if isinstance(existing, ThinkSubgraphCarry):
        return existing
    return ThinkSubgraphCarry(state=context.state)


@dataclass(frozen=True, slots=True)
class ThinkReasonExecutor:
    """think 节点:调 Reasoner 生成候选 Decision。"""

    semantic_name: str = _SEMANTIC_NAME

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        # 老 PhaseExecutor 路径(保留 carry 语义,兼容 tests + 老 caller)
        carry = _carry(context)
        reasoner = context.capabilities.get("phase.think.reason")
        if reasoner is None:
            return PhaseResult(result_kind=STAGE_KIND, payload=carry)
        assert isinstance(reasoner, Reasoner), (  # noqa: S101
            "phase.think.reason must implement Reasoner"
        )
        response = await run_reasoner_with_spine_facts(reasoner, carry.state)
        return PhaseResult(
            result_kind=STAGE_KIND,
            payload=replace(carry, response=response),
        )

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """think 子图节点入口。

        inputs 端口(yaml):messages, tools
        outputs 端口(yaml):response
        """
        runtime = context.runtime
        state = runtime.get("state") if isinstance(runtime, dict) else None
        reasoner = runtime.get("reasoner") if isinstance(runtime, dict) else None

        if reasoner is None or state is None:
            return NodeOutput(port_values={})

        assert isinstance(reasoner, Reasoner), (  # noqa: S101
            "think.reason runtime['reasoner'] must implement Reasoner"
        )
        response = await run_reasoner_with_spine_facts(reasoner, state)
        return NodeOutput(port_values={"response": response})


@plugin(
    id="phase.think.reason",
    Config=StandardPhaseConfig,
    provides=("phase.think.reason",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/think/test_reason_phase_plugin.py",
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
                "phase_think_reason.checked",
                "phase_think_reason.served",
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
    executor = ThinkReasonExecutor()
    ctx.provide("phase.think.reason", executor)
    get_default_registry().register(
        executor,
        semantic_name=_SEMANTIC_NAME,
        region=_REGION,
    )


def create_executor() -> ThinkReasonExecutor:
    return ThinkReasonExecutor()


__all__ = ["ThinkReasonExecutor", "create_executor", "setup"]
