"""Gateway 生产组队 —— solo 裸模型 + team LLM casting（ADR-0052）。"""

from __future__ import annotations

from gateway.modes import SOLO_ROLE
from lca.contracts.models.observability.journal import (
    CastingCompleted,
    CastingFailed,
    CastingStarted,
    RunScope,
)
from lca.contracts.protocols import LLMAdapter, ObservabilityBackend
from lca.contracts.protocols.casting import CastingError, RoleLibrary, TeamCaster
from lca.layer0_infra.observability import (
    ObservabilityHub,
    bind,
    objective_preview,
    record,
    run_scope,
)
from lca.layer0_infra.tools.default_set import build_g2a_chat_tools
from lca.layer3_agent.role_library import FileRoleLibrary
from lca.layer4_app.api import Agent, Team
from lca.layer4_app.casting import LLMTeamCaster, build_from_casting_plan


def build_solo_agent(
    llm: LLMAdapter,
    *,
    observability: ObservabilityBackend,
) -> Agent:
    """Solo 裸模型（ADR-0052）：零角色概念，对齐 LobeHub systemRole=''。

    role 只设一个最小标签（"助手"），goal/backstory 留空 —— prompt 渲染侧
    空字段不渲染对应 section，等同于无 system prompt。
    """
    return Agent(
        role=SOLO_ROLE,
        goal="",
        backstory="",
        tools=build_g2a_chat_tools(),
        llm=llm,
        observability=observability,
    )


async def build_runnable_team(
    objective: str,
    llm: LLMAdapter,
    *,
    observability: ObservabilityHub,
    trace_id: str,
    run_id: str,
    library: RoleLibrary | None = None,
    caster: TeamCaster | None = None,
) -> Team:
    """Team LLM casting（ADR-0042）：选角 + 治理判定 + 编译成 Team。

    library/caster 可注入供测试替换；生产路径用 FileRoleLibrary（扫描
    AGENCY_ROLES_DIR 或内置 roles/）与 LLMTeamCaster。
    """
    resolved_library = library if library is not None else FileRoleLibrary()
    resolved_caster = caster if caster is not None else LLMTeamCaster()
    scope = RunScope(trace_id=trace_id, run_id=run_id)
    with bind(observability), run_scope(scope):
        record(CastingStarted(objective_preview=objective_preview(objective)))
        try:
            plan = await resolved_caster.cast(objective, resolved_library, llm)
        except CastingError as exc:
            record(CastingFailed(error=str(exc)))
            raise
        selected_roles = tuple(
            resolved_library.get(chosen.role_id).title for chosen in plan.selected
        )
        record(
            CastingCompleted(
                governance_kind=plan.governance_kind,
                lead_role=plan.lead_role_id or "",
                selected_roles=selected_roles,
                rationale=plan.rationale,
            )
        )
    return build_from_casting_plan(plan, resolved_library, llm, observability=observability)
