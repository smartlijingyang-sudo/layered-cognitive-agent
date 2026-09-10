"""phase.think.route — SkillRouter picks active template; Reducer folds state.

think 子图节点 plugin:运行时动态选择 Prompt 模板并折叠 AgentState。
``requires=("skill_router",)`` 通过 Cordis 校验,
运行时从 ``context.runtime.skill_router`` 拿 capability 实例。

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
from lca.contracts.protocols.think.cognition import SkillRouter
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class ThinkRouteExecutor:
    """think 节点:从 SkillRouter 选 active template,由 Reducer 折叠 state。"""

    semantic_name: str = "think.route"
    region: str = "phase:think"
    # ADR-0219 §5.5: typed port contract declared on the plugin (graph
    # layer does not know port names; it only knows topology).
    declared_inputs: tuple[PortName, ...] = ("in_assembled_manifest",)
    declared_outputs: tuple[PortName, ...] = ("route_choice", "enforced_state")

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
        state = runtime.state
        router = runtime.skill_router
        reducer = runtime.reducer

        if router is None or state is None:
            return NodeOutput(port_values={})

        assert isinstance(router, SkillRouter), (  # noqa: S101
            "think.route runtime.skill_router must implement SkillRouter"
        )
        if reducer is None:
            raise RuntimeError(
                "think.route requires runtime.reducer when a SkillRouter is configured"
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
    Config=None,
    provides=("phase.think.route",),
    requires=("skill_router",),
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
                "phase_think_route.checked",
                "phase_think_route.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve", "skill_router"),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """双键注册:Cordis provide(composite + region-less)。"""
    del config
    executor = ThinkRouteExecutor()
    # Composite key for region-scoped resolution (preferred)
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)
    # Region-less fallback for cross-region reuse
    ctx.provide(executor.semantic_name, executor)


__all__ = ["ThinkRouteExecutor", "setup"]
