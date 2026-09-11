"""phase.think.reason.render — adapter from (state, plan) to typed render_turn.

think.reason inner_graph 第 2 节点 plugin:把 compat-era ``(state, plan)``
喂给 ``Reasoner.render_turn``,但 ADR-0220 §6 P4 已经把 ``render_turn`` 改成
``(context, template, role) -> ReasonerTurnRender`` typed 入口。本节点负责
在 seam 上做一次 state → typed-DTO 适配 —— 业务真实路径走
``concept.prompt.render`` 图,这里只是 inner_graph 的过渡适配,被 P5
``agent.reasoning.turn`` 取代。

``requires=("reasoner",)`` 通过 Cordis 校验,运行时从
``context.runtime.reasoner`` 拿 capability 实例。
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
from lca.contracts.models.cognition.boundary import (
    ReasonerContext,
    RoleSnapshot,
    TemplateSelection,
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


def _state_to_boundary(
    state: object,
    plan: object,
    role_profile: object,
) -> tuple[ReasonerContext, TemplateSelection, RoleSnapshot]:
    """Translate the legacy (state, plan) adapter inputs into typed DTOs.

    Each input is duck-typed so the adapter stays tolerant of the
    partial ``AgentState`` shapes the inner-graph tests build. When the
    legacy fields are missing we fall back to empty defaults; the
    downstream ``Reasoner.render_turn`` decides whether that's enough.
    """
    task = getattr(state, "task", "") or ""
    activated = getattr(state, "activated_skills", ()) or ()
    manifest = getattr(state, "manifest", None)
    awareness = getattr(state, "team_awareness", None)
    template_id = getattr(plan, "template_id", "") or ""
    decision_path = getattr(plan, "decision_path", "legacy")
    variant = getattr(plan, "variant_preview", None)
    context = ReasonerContext(
        task=task,
        activated_skills=tuple(activated),
        manifest=manifest,
    )
    selection = TemplateSelection(
        template_id=template_id,
        variant=variant if variant in ("react", "hierarchical", "routing", "casting") else "react",
        decision_path=decision_path,
    )
    snapshot = RoleSnapshot(profile=role_profile, team_awareness=awareness)
    return context, selection, snapshot


@dataclass(frozen=True, slots=True)
class ThinkReasonRenderExecutor:
    """think.reason inner_graph 第 2 节点:从 (state, plan) 算 ReasonerTurnRender。

    ADR-0220 P4:适配 (state, plan) → typed DTO 三元组 → reasoner.render_turn。
    """

    semantic_name: str = "think.reason.render"
    region: str = "phase:think"
    # ADR-0219 §5.5: typed port contract declared on the plugin (graph
    # layer does not know port names; it only knows topology).
    declared_inputs: tuple[PortName, ...] = ("turn_plan",)
    declared_outputs: tuple[PortName, ...] = ("turn_render",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """think.reason.render 入口。

        inputs 端口(yaml):turn_plan
        outputs 端口(yaml):turn_render
        """
        runtime = context.runtime
        state = runtime.state
        reasoner = runtime.reasoner
        plan = input.port_values.get("turn_plan")

        if reasoner is None or state is None or plan is None:
            return NodeOutput(port_values={})

        render_turn = getattr(reasoner, "render_turn", None)
        if not callable(render_turn):
            return NodeOutput(port_values={})

        role_profile = getattr(reasoner, "role_profile", None)
        boundary = _state_to_boundary(state, plan, role_profile)
        render = render_turn(*boundary)
        return NodeOutput(port_values={"turn_render": render})


@plugin(
    id="phase.think.reason.render",
    Config=None,
    provides=("phase:think::think.reason.render",),
    requires=("reasoner",),
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
                "phase_think_reason_render.checked",
                "phase_think_reason_render.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve", "reasoner"),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Composite-key 注册:``{region}::{semantic_name}``。"""
    del config
    executor = ThinkReasonRenderExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ThinkReasonRenderExecutor", "setup"]
