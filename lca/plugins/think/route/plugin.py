"""phase.think.route — SkillRouter picks active template; Reducer folds state.

ADR-0217 §3.3:本 plugin 实现 NodeExecutor 协议(think 子图专用),同时保留
@plugin(...) 装饰器注册(Cordis 容器兼容)。双注册互不替代:
- @plugin(...) → Cordis 容器 / 老 caller
- FactoryRegistry.register → NodeExecutor 解析 / think 子图 caller
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
from lca.contracts.protocols import SkillRouter
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
from lca.plugins.loop.phase._shared.common import StandardPhaseConfig

_SEMANTIC_NAME = "think.route"
_REGION = "phase:think"

STAGE_KIND = "think_stage"

SPEC = step_plugin_spec(
    plugin_id="phase.think.route",
    module="lca.plugins.think.route.plugin",
    test_suite="tests/think/test_route_phase_plugin.py",
)


def _carry(context: PhaseContext) -> ThinkSubgraphCarry:
    """老 caller 兼容:从 context.artifacts 取/新建 ThinkSubgraphCarry。"""
    existing = context.artifacts.get(CARRY_KEY)
    if isinstance(existing, ThinkSubgraphCarry):
        return existing
    return ThinkSubgraphCarry(state=context.state)


@dataclass(frozen=True, slots=True)
class ThinkRouteExecutor:
    """think 节点:从 SkillRouter 选 active template,由 Reducer 折叠 state。"""

    semantic_name: str = _SEMANTIC_NAME

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        # 老 PhaseExecutor 路径(保留 carry 语义,兼容 tests + 老 caller)
        carry = _carry(context)
        router = context.capabilities.get("phase.think.route")
        if router is None:
            return PhaseResult(result_kind=STAGE_KIND, payload=carry)
        assert isinstance(router, SkillRouter), (  # noqa: S101
            "phase.think.route must implement SkillRouter"
        )
        reducer = context.capabilities.get("phase.think.reducer")
        if reducer is None:
            raise RuntimeError(
                "phase.think.route requires phase.think.reducer when a SkillRouter is configured"
            )
        apply_skill_route = getattr(reducer, "apply_skill_route", None)
        if not callable(apply_skill_route):
            raise RuntimeError(
                "phase.think.reducer must expose apply_skill_route(state, active_template)"
            )
        active_template = await router.route(carry.state)
        routed_state = apply_skill_route(carry.state, active_template)
        return PhaseResult(
            result_kind=STAGE_KIND,
            payload=replace(carry, state=routed_state),
        )

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """think 子图节点入口。

        inputs 端口(yaml):in_assembled_manifest
        outputs 端口(yaml):route_choice, enforced_state
        """
        runtime = context.runtime
        state = runtime.get("state") if isinstance(runtime, dict) else None
        router = runtime.get("skill_router") if isinstance(runtime, dict) else None
        reducer = runtime.get("reducer") if isinstance(runtime, dict) else None

        if router is None or state is None:
            return NodeOutput(port_values={})

        assert isinstance(router, SkillRouter), (  # noqa: S101
            "think.route runtime['skill_router'] must implement SkillRouter"
        )
        if reducer is None:
            raise RuntimeError(
                "think.route requires runtime['reducer'] when a SkillRouter is configured"
            )
        apply_skill_route = getattr(reducer, "apply_skill_route", None)
        if not callable(apply_skill_route):
            raise RuntimeError(
                "think.route reducer must expose apply_skill_route(state, active_template)"
            )
        active_template = await router.route(state)
        routed_state = apply_skill_route(state, active_template)
        return NodeOutput(
            port_values={
                "route_choice": active_template,
                "enforced_state": routed_state,
            },
        )


@plugin(
    id="phase.think.route",
    Config=StandardPhaseConfig,
    provides=("phase.think.route",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/think/test_route_phase_plugin.py",
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
                "phase_think_route.checked",
                "phase_think_route.served",
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
    executor = ThinkRouteExecutor()
    ctx.provide("phase.think.route", executor)
    get_default_registry().register(
        executor,
        semantic_name=_SEMANTIC_NAME,
        region=_REGION,
    )


def create_executor() -> ThinkRouteExecutor:
    return ThinkRouteExecutor()


__all__ = ["ThinkRouteExecutor", "create_executor", "setup"]
