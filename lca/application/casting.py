"""自动组队默认实现（ADR-0042）：LLMTeamCaster + CastingPlan → Team 编译。

分工：``cast()`` 是唯一异步、不确定的步骤（一次结构化 LLM 调用 + 白名单
校验 + 一次纠正重试）；``build_from_casting_plan()`` 是纯同步翻译，与手写
``Agent(role=..., goal=..., backstory=...)`` + ``Team(...)`` 走完全相同的
路径——组合根不感知角色是人选的还是 LLM 选的。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

import structlog

from lca.contracts.models.team.team_coordination import (
    STRATEGY_KEY_DEBATE,
    STRATEGY_KEY_FAN_OUT,
    STRATEGY_KEY_PEER_RELAY,
    STRATEGY_KEY_PEER_SWARM,
    STRATEGY_KEY_PIPELINE,
    Coordination,
    Debate,
    FanOut,
    LeadMandate,
    PeerRelay,
    PeerSwarm,
    Pipeline,
)
from lca.contracts.protocols.casting import (
    CASTING_GOVERNANCE_KINDS,
    CASTING_MAX_ROLES,
    CASTING_MIN_ROLES,
    LEAD_CASTING_KINDS,
    CastingError,
    CastingPlan,
    CastingPromptRenderer,
    RoleCard,
    RoleIndexEntry,
    RoleLibrary,
    SelectedRole,
    TeamCaster,
)
from lca.contracts.protocols.infra import LLMAdapter, Tool
from lca.contracts.protocols.observability import ObservabilityBackend
from lca.contracts.protocols.spec import OBSERVABILITY_CHOICE_CONSOLE
from lca.application.api import Agent, Team, TeamLead
from lca.application.role_suggest import suggest_for_auto_repair, suggest_from_paths

if TYPE_CHECKING:
    from cordis import Context

logger = structlog.get_logger(__name__)


def _extract_json_block(raw_output: str) -> str:
    """从 LLM 原始输出提取 JSON 文本（平衡括号匹配 → 整段 parse → ```json 围栏）。"""
    import re

    start = raw_output.find("{")
    if start >= 0:
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(raw_output)):
            ch = raw_output[index]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return raw_output[start : index + 1].strip()
    stripped = raw_output.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw_output, re.DOTALL)
    if m:
        return m.group(1).strip()
    return stripped


CASTING_PROMPT_NAME = "casting_prompt"
_OBJECTIVE_PLACEHOLDER = "{objective}"
_CATALOG_PLACEHOLDER = "{role_catalog}"
_CASTING_ATTEMPTS = 2
"""首次生成 + 一次带纠正提示的重试。"""

_LEAD_MANDATE_BY_KIND: dict[str, LeadMandate] = {mandate.value: mandate for mandate in LeadMandate}
_COORDINATION_FACTORY: dict[str, Callable[[], Coordination]] = {
    STRATEGY_KEY_PIPELINE: Pipeline,
    STRATEGY_KEY_FAN_OUT: FanOut,
    STRATEGY_KEY_PEER_RELAY: PeerRelay,
    STRATEGY_KEY_PEER_SWARM: PeerSwarm,
    STRATEGY_KEY_DEBATE: Debate,
}
"""治理词表 → Coordination 工厂注册表：声明式分发，禁止 if/else 链。"""


class LLMTeamCaster(TeamCaster):
    """LLM TeamCaster：结构化调用、白名单校验和受 profile 选择的提示词。

    白名单校验（role_id ∈ 角色库、governance.kind ∈ 既有封闭词表）顺带构成
    prompt injection 防线：objective 是用户输入，LLM 输出中任何越界值一律
    拒绝，不存在借选角越权的口子。
    """

    def __init__(self, prompt_renderer: CastingPromptRenderer) -> None:
        """Bind the prompt content policy explicitly at plugin composition time."""

        self._prompt_renderer = prompt_renderer

    async def cast(self, objective: str, library: RoleLibrary, llm: LLMAdapter) -> CastingPlan:
        prompt = render_casting_prompt(objective, library.index(), self._prompt_renderer)
        last_error = "no attempt made"
        for attempt in range(_CASTING_ATTEMPTS):
            response = await llm.complete(prompt)
            plan, error = parse_casting_output(response.text, library)
            if plan is not None:
                return plan
            last_error = error
            logger.info("casting_rejected", attempt=attempt + 1, error=error)
            prompt = (
                f"{prompt}\n\n你上一次的输出被拒绝，原因：{error}。"
                f"{_format_casting_correction_hint(error, library)}"
                "请按规则重新输出修正后的完整 JSON。"
            )
        raise CastingError(f"自动组队失败：{last_error}")


def render_casting_prompt(
    objective: str,
    index: tuple[RoleIndexEntry, ...],
    renderer: CastingPromptRenderer,
) -> str:
    """Render the selected prompt through the profile-bound renderer capability."""

    return renderer.render(objective, index)


def _format_casting_correction_hint(error: str, library: RoleLibrary) -> str:
    """为重试 prompt 附加 AO 风格的「你是不是想用 X」定向替换提示。"""
    prefix = "以下 role_id 不在角色库中："
    if not error.startswith(prefix):
        return ""
    unknown = [part.strip() for part in error[len(prefix) :].split(",") if part.strip()]
    if not unknown:
        return ""
    valid_ids = [entry.role_id for entry in library.index()]
    lines: list[str] = []
    for bad in unknown:
        suggestions = suggest_from_paths(bad, valid_ids)
        suggestion = suggestions[0] if suggestions else None
        if suggestion:
            lines.append(f'  - {bad} → 请改用 "{suggestion}"')
        else:
            lines.append(f"  - {bad}")
    if not lines:
        return ""
    return "\n角色路径纠正（必须严格使用角色库中的 path）：\n" + "\n".join(lines) + "\n"


def parse_casting_output(raw_output: str, library: RoleLibrary) -> tuple[CastingPlan | None, str]:
    """解析 + 白名单校验 LLM 输出；失败返回 (None, 可回喂给 LLM 的原因)。"""
    try:
        data = json.loads(_extract_json_block(raw_output))
    except (json.JSONDecodeError, ValueError) as exc:
        return None, f"输出不是合法 JSON：{exc}"
    if not isinstance(data, dict):
        return None, "输出必须是 JSON 对象"
    repaired, replacements = repair_invalid_role_ids(data, library)
    if replacements:
        logger.info(
            "casting_auto_repaired_roles",
            replacements=[{"from": src, "to": dst} for src, dst in replacements],
        )
        data = repaired
    return _validate_payload(data, library)


def repair_invalid_role_ids(
    data: dict[str, Any],
    library: RoleLibrary,
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """确定性修复幻觉 role_id（对齐 AO compose repairInvalidRolesInYaml 思路）。"""
    raw_selected = data.get("selected")
    if not isinstance(raw_selected, list):
        return data, []

    valid_ids = [entry.role_id for entry in library.index()]
    if not valid_ids:
        return data, []

    replacements: list[tuple[str, str]] = []
    new_selected: list[Any] = []
    for item in raw_selected:
        if not isinstance(item, dict):
            new_selected.append(item)
            continue
        role_id = str(item.get("role_id", "")).strip()
        if role_id and role_id not in valid_ids:
            suggestion = suggest_for_auto_repair(role_id, valid_ids)
            if suggestion:
                replacements.append((role_id, suggestion))
                item = {**item, "role_id": suggestion}
        new_selected.append(item)

    if not replacements:
        return data, []
    return {**data, "selected": new_selected}, replacements


def _validate_payload(data: dict[str, Any], library: RoleLibrary) -> tuple[CastingPlan | None, str]:
    valid_ids = {entry.role_id for entry in library.index()}

    raw_selected = data.get("selected")
    if not isinstance(raw_selected, list) or not raw_selected:
        return None, "selected 必须是非空数组"
    if not CASTING_MIN_ROLES <= len(raw_selected) <= CASTING_MAX_ROLES:
        return None, f"角色数量必须在 {CASTING_MIN_ROLES}-{CASTING_MAX_ROLES} 之间"

    selected: list[SelectedRole] = []
    seen: set[str] = set()
    unknown: list[str] = []
    for item in raw_selected:
        if not isinstance(item, dict):
            return None, "selected 条目必须是对象"
        role_id = str(item.get("role_id", "")).strip()
        if not role_id:
            return None, "selected 条目缺少 role_id"
        if role_id in seen:
            return None, f"角色重复：{role_id}"
        if role_id not in valid_ids:
            unknown.append(role_id)
        seen.add(role_id)
        hint = item.get("task_hint")
        selected.append(
            SelectedRole(role_id=role_id, task_hint=str(hint).strip() or None if hint else None)
        )
    if unknown:
        return None, f"以下 role_id 不在角色库中：{', '.join(unknown)}"

    governance = data.get("governance")
    if not isinstance(governance, dict):
        return None, "缺少 governance 对象"
    kind = str(governance.get("kind", "")).strip()
    if kind not in CASTING_GOVERNANCE_KINDS:
        return None, f"governance.kind 必须是 {sorted(CASTING_GOVERNANCE_KINDS)} 之一"

    lead_role_id = governance.get("lead_role_id")
    lead_role_id = str(lead_role_id).strip() if lead_role_id else None
    if kind in LEAD_CASTING_KINDS:
        if lead_role_id is None:
            return None, f"lead 类治理（{kind}）必须指定 lead_role_id"
        if lead_role_id not in seen:
            return None, f"lead_role_id {lead_role_id} 必须在 selected 中"
    elif lead_role_id is not None:
        return None, f"无主导者治理（{kind}）不得指定 lead_role_id"

    return CastingPlan(
        selected=tuple(selected),
        governance_kind=kind,
        lead_role_id=lead_role_id,
        rationale=str(data.get("rationale", "")),
    ), ""


def build_from_casting_plan(
    plan: CastingPlan,
    library: RoleLibrary,
    llm: LLMAdapter,
    *,
    observability: str | ObservabilityBackend = OBSERVABILITY_CHOICE_CONSOLE,
    scope: Context | None = None,
    tools: Sequence[Tool],
) -> Team:
    """Compile a validated casting plan using the caller-materialized tools.

    Tool materialization belongs to the profile's ``tools`` capability at the
    run-assembly boundary. This translator only projects the selected tool set
    onto each member, so it cannot recreate a concrete default tool provider.
    """
    cards: dict[str, tuple[RoleCard, str | None]] = {
        chosen.role_id: (library.get(chosen.role_id), chosen.task_hint) for chosen in plan.selected
    }
    member_tools = tuple(tools)

    def _member(role_id: str) -> Agent:
        card, task_hint = cards[role_id]
        goal = f"{card.summary}。本次任务：{task_hint}" if task_hint else card.summary
        return Agent(
            role=card.title,
            goal=goal,
            backstory=card.backstory,
            tools=member_tools,
            llm=llm,
            observability=observability,
            scope=scope,
        )

    if plan.governance_kind in _LEAD_MANDATE_BY_KIND:
        if plan.lead_role_id is None:  # 白名单校验已保证，此处防御式兜底
            raise CastingError("lead 类治理缺少 lead_role_id")
        lead_agent = _member(plan.lead_role_id)
        members = [_member(role_id) for role_id in cards if role_id != plan.lead_role_id]
        return Team(
            members=members,
            lead=TeamLead(lead_agent, _LEAD_MANDATE_BY_KIND[plan.governance_kind]),
            observability=observability,
            scope=scope,
        )

    factory = _COORDINATION_FACTORY.get(plan.governance_kind)
    if factory is None:  # 同上：白名单校验已保证
        raise CastingError(f"未知治理方式：{plan.governance_kind!r}")
    members = [_member(chosen.role_id) for chosen in plan.selected]
    return Team(members=members, coordination=factory(), observability=observability, scope=scope)
