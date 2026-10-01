"""phase.think.reason.render — adapter from (state, plan) to typed render_turn.

think.reason inner_graph 第 2 节点 plugin:把 compat-era ``(state, plan)``
喂给 ``Reasoner.render_turn``,但 ADR-0220 §6 P4 已经把 ``render_turn`` 改成
``(context, template, role) -> ReasonerTurnRender`` typed 入口。本节点负责
在 seam 上做一次 state → typed-DTO 适配 —— 业务真实路径走
``concept.prompt.render`` 图,这里只是 inner_graph 的过渡适配,被 P5
``agent.reasoning.turn`` 取代。

``requires``(无 Cordis capability 读):role 从
``context.runtime.brain.role_profile`` 读,不再从
``PromptReasoner.role_profile`` 字段读(eng/retire-v1-reasoner-sandbox)。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, cast

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
from lca.contracts.models.core.perceive.projection import current_manifest_from_state
from lca.contracts.models.team.role.team import RoleProfile
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

_log = logging.getLogger(__name__)


def _refresh_role_profile(
    runtime: object,
    role_profile: RoleProfile | None,
) -> RoleProfile | None:
    """Re-read the standing files when the run is bound to an assistant home.

    The injected ``standing_refresher`` returns the freshly assembled
    backstory from disk. Without a refresher, without ``bindings.home_path``,
    or when the refresh fails, the original profile is kept unchanged.
    """
    refresher = _resolve_refresher(runtime)
    if not callable(refresher):
        return role_profile
    try:
        from lca.infrastructure.runtime_plane.capability_bindings import (
            current_bindings_view,
        )

        bindings = current_bindings_view()
    except Exception:
        return role_profile
    home_path = getattr(bindings, "home_path", None) if bindings is not None else None
    if not home_path:
        return role_profile
    fallback = str(getattr(role_profile, "backstory", "") or "")
    refreshed = refresher(home_path, fallback=fallback)
    if not refreshed or refreshed == fallback:
        return role_profile
    if role_profile is None:
        return role_profile
    return replace(role_profile, backstory=refreshed)


def _resolve_refresher(runtime: object) -> Any:
    """Read the ``standing_refresher`` capability off the runtime view."""

    refresher = getattr(runtime, "standing_refresher", None)
    if refresher is None:
        get = getattr(runtime, "get", None)
        if callable(get):
            refresher = get("standing_refresher")
    return refresher


def _state_to_boundary(
    state: object,
    plan: object,
    role_profile: RoleProfile,
) -> tuple[ReasonerContext, TemplateSelection, RoleSnapshot]:
    """Translate the legacy (state, plan) adapter inputs into typed DTOs.

    Each input is duck-typed so the adapter stays tolerant of the
    partial ``AgentState`` shapes the inner-graph tests build. When the
    legacy fields are missing we fall back to empty defaults; the
    downstream ``Reasoner.render_turn`` decides whether that's enough.
    """
    task = getattr(state, "task", "") or ""
    activated = getattr(state, "activated_skills", ()) or ()
    manifest = current_manifest_from_state(state) if state is not None else None
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
        decision_path=(
            decision_path
            if decision_path
            in (
                "active_template_override",
                "consult_duty",
                "team_awareness_routing",
                "profile_default",
                "legacy",
            )
            else "legacy"
        ),
    )
    snapshot = RoleSnapshot(profile=role_profile, team_awareness=awareness)
    return context, selection, snapshot


def _resolve_role_profile(runtime: object) -> RoleProfile | None:
    """Read ``role_profile`` off ``runtime.brain`` (typed Brain attribute).

    PromptReasoner no longer owns RoleProfile (eng/retire-v1-reasoner-sandbox);
    the Brain Protocol exposes it as a typed ``brain.role_profile`` attribute,
    populated at AgentSpec composition time. This adapter reads it via the
    Brain attribute, which is the typed single-step access path. Falls back
    to the reasoner's own ``role_profile`` field when the brain is not wired
    or when Brain is not a typed instance (compat path for older reasoner
    stubs).
    """
    brain = getattr(runtime, "brain", None)
    if brain is not None:
        direct = getattr(brain, "role_profile", None)
        if direct is not None:
            return direct
    reasoner = getattr(runtime, "reasoner", None)
    if reasoner is None:
        brain = getattr(runtime, "brain", None)
        if brain is not None:
            reasoner = getattr(brain, "reasoner", None)
    return getattr(reasoner, "role_profile", None)


@dataclass(frozen=True, slots=True)
class ThinkReasonRenderExecutor:
    """think.reason inner_graph 第 2 节点:从 (state, plan) 算 ReasonerTurnRender。

    ADR-0220 P4:适配 (state, plan) → typed DTO 三元组 → reasoner.render_turn。
    """

    semantic_name: str = "think.reason.render"
    region: str = "think"
    # ADR-0219 §5.5: typed port contract declared on the plugin (graph
    # layer does not know port names; it only knows topology).
    declared_inputs: tuple[PortName, ...] = (PortName("turn_plan"),)
    declared_outputs: tuple[PortName, ...] = (PortName("turn_render"),)

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
        state = getattr(runtime, "state", None)
        brain = getattr(runtime, "brain", None)
        reasoner = getattr(brain, "reasoner", None) if brain is not None else None
        plan = input.port_values.get(PortName("turn_plan"))
        render_turn = getattr(reasoner, "render_turn", None) if reasoner is not None else None
        role_profile = _resolve_role_profile(runtime)
        role_profile = _refresh_role_profile(runtime, role_profile)
        missing = [
            name
            for name, value in (
                ("context.runtime.state", state),
                ("context.runtime.brain.reasoner", reasoner),
                ("reasoner.render_turn", render_turn if callable(render_turn) else None),
                ("brain.role_profile", role_profile),
                ("'turn_plan' port", plan),
            )
            if value is None
        ]
        if missing:
            # Fail loud: an unrendered turn means history.assemble has no
            # system prompt to source, and the model would be dispatched
            # without identity or rules (spec §G). Returning empty ports
            # here hid exactly that for a whole run.
            raise RuntimeError(
                f"think.reason.render: cannot render the turn prompt — missing {', '.join(missing)}"
            )
        # The fail-loud check above guarantees role_profile is present and
        # render_turn is callable; the runtime view itself is untyped.
        boundary = _state_to_boundary(state, plan, cast("RoleProfile", role_profile))
        render = cast("Callable[..., Any]", render_turn)(*boundary)
        _log.debug(
            "think.reason.render emitted turn_render variant=%s section_count=%s",
            getattr(render, "variant", None),
            getattr(render, "section_count", None),
        )
        return NodeOutput(port_values={PortName("turn_render"): render})


@plugin(
    id="phase.think.reason.render",
    Config=None,
    provides=("think::think.reason.render",),
    # PR-C: legacy Cordis requires removed —
    # PR-A routes via ``runtime.brain.reasoner`` and
    # ``runtime.brain.role_profile`` (typed Protocol access), no Cordis seam.
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
                "phase_think_reason_render.checked",
                "phase_think_reason_render.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        # PR-C: the legacy Cordis capability reads were dropped; the node
        # reads ``runtime.brain.reasoner`` and ``runtime.brain.role_profile``
        # (typed Protocol access).
        reads=("plugin.serve",),
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
