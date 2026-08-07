"""Gateway 协作模式目录 —— UI 与生产组队的单一事实源。

测试 CLI 探针（``tests/harness/modes.py``）保留 Alice/Bob 剧本用于确定性探针；
本模块定义面向真实用户的产品角色与示例任务。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from lca.contracts.models.team.team_coordination import DEFAULT_COORDINATION_MAX_ROUNDS


@dataclass(frozen=True)
class AgentRoleTemplate:
    """可复用的 Agent 角色模板（role / goal / backstory）。"""

    role: str
    goal: str
    backstory: str


@dataclass(frozen=True)
class ModeDefinition:
    """一种协作模式的生产组队定义。"""

    key: str
    help_text: str
    has_lead: bool
    example_prompts: tuple[str, ...]
    member_roles: tuple[AgentRoleTemplate, ...]
    lead_role: AgentRoleTemplate | None = None
    coordination: str | None = None
    max_rounds: int = DEFAULT_COORDINATION_MAX_ROUNDS


TEAM_LEAD = AgentRoleTemplate(
    role="团队负责人",
    goal="拆解任务、协调成员并汇总最终结论",
    backstory="擅长跨职能协作与决策收口",
)

TECH_ADVISOR = AgentRoleTemplate(
    role="技术顾问",
    goal="从技术可行性、风险与实施成本角度分析问题",
    backstory="资深工程师，擅长系统架构与工程实践",
)

BUSINESS_ADVISOR = AgentRoleTemplate(
    role="业务顾问",
    goal="从商业价值、用户影响与合规角度评估方案",
    backstory="业务负责人，关注 ROI 与市场接受度",
)

OPERATIONS_ADVISOR = AgentRoleTemplate(
    role="运营顾问",
    goal="从落地执行与资源配置角度补充建议",
    backstory="运营专家，擅长将策略转化为可执行计划",
)

SOLO_ANALYST = AgentRoleTemplate(
    role="独立分析师",
    goal="独立分析用户问题并给出清晰结论",
    backstory="多领域咨询背景，擅长结构化表达",
)

MODE_DEFINITIONS: Final[dict[str, ModeDefinition]] = {
    "routing": ModeDefinition(
        key="routing",
        help_text="有主导 · Lead 显式委派成员后收口",
        has_lead=True,
        example_prompts=(
            "评估新功能上线的技术风险与业务影响",
            "制定季度产品路线图的关键里程碑",
        ),
        member_roles=(TECH_ADVISOR, BUSINESS_ADVISOR),
        lead_role=TEAM_LEAD,
        coordination=None,
    ),
    "consult": ModeDefinition(
        key="consult",
        help_text="有主导 · Lead 咨询成员后自己决定",
        has_lead=True,
        example_prompts=(
            "是否应在本周发布灰度版本？",
            "选择云厂商时应优先考虑哪些因素？",
        ),
        member_roles=(TECH_ADVISOR, BUSINESS_ADVISOR),
        lead_role=TEAM_LEAD,
        coordination=None,
    ),
    "board": ModeDefinition(
        key="board",
        help_text="有主导 · 全员咨询后 Lead 收口",
        has_lead=True,
        example_prompts=(
            "是否将客服机器人切换到新模型？",
            "是否批准下一轮融资的使用计划？",
        ),
        member_roles=(TECH_ADVISOR, BUSINESS_ADVISOR),
        lead_role=TEAM_LEAD,
        coordination=None,
    ),
    "pipeline": ModeDefinition(
        key="pipeline",
        help_text="无主导 · 成员顺序接力",
        has_lead=False,
        example_prompts=(
            "起草并优化一条营销短信",
            "把用户反馈整理成可执行的行动清单",
        ),
        member_roles=(TECH_ADVISOR, BUSINESS_ADVISOR, OPERATIONS_ADVISOR),
        coordination="pipeline",
    ),
    "fan_out": ModeDefinition(
        key="fan_out",
        help_text="无主导 · 并行执行再合成",
        has_lead=False,
        example_prompts=(
            "从效率、协作、文化三个角度分析远程办公",
            "并行评估三种技术方案后给出推荐",
        ),
        member_roles=(TECH_ADVISOR, BUSINESS_ADVISOR, OPERATIONS_ADVISOR),
        coordination="fan_out",
    ),
    "peer_relay": ModeDefinition(
        key="peer_relay",
        help_text="无主导 · 点对点接力",
        has_lead=False,
        example_prompts=(
            "从现象到根因，分析用户登录变慢的问题",
            "逐步细化一项 MVP 的功能范围",
        ),
        member_roles=(TECH_ADVISOR, BUSINESS_ADVISOR),
        coordination="peer_relay",
    ),
    "peer_swarm": ModeDefinition(
        key="peer_swarm",
        help_text="无主导 · 对等多轮 swarm",
        has_lead=False,
        example_prompts=(
            "共同拟定一个产品 slogan",
            "讨论并收敛一份发布检查清单",
        ),
        member_roles=(TECH_ADVISOR, BUSINESS_ADVISOR),
        coordination="peer_swarm",
        max_rounds=2,
    ),
    "debate": ModeDefinition(
        key="debate",
        help_text="无主导 · 多轮辩论",
        has_lead=False,
        example_prompts=(
            "辩论是否应强制双因素认证",
            "正反方讨论是否采用微服务架构",
        ),
        member_roles=(TECH_ADVISOR, BUSINESS_ADVISOR),
        coordination="debate",
        max_rounds=2,
    ),
    "graph": ModeDefinition(
        key="graph",
        help_text="无主导 · 执行图 ENTRY→agents→EXIT",
        has_lead=False,
        example_prompts=(
            "生成一份每日站会议程",
            "按固定流程完成需求评审摘要",
        ),
        member_roles=(TECH_ADVISOR, BUSINESS_ADVISOR),
        coordination="graph",
    ),
    "solo": ModeDefinition(
        key="solo",
        help_text="单 Agent（无 Team）",
        has_lead=False,
        example_prompts=(
            "用三句话解释这个技术选型的利弊",
            "帮我列一份决策 checklist",
        ),
        member_roles=(SOLO_ANALYST,),
        coordination=None,
    ),
}

ALL_MODES: Final[tuple[str, ...]] = tuple(MODE_DEFINITIONS.keys())

MODE_HELP: Final[dict[str, str]] = {
    key: definition.help_text for key, definition in MODE_DEFINITIONS.items()
}

MODE_HAS_LEAD: Final[dict[str, bool]] = {
    key: definition.has_lead for key, definition in MODE_DEFINITIONS.items()
}

EXAMPLE_PROMPTS: Final[dict[str, tuple[str, ...]]] = {
    key: definition.example_prompts for key, definition in MODE_DEFINITIONS.items()
}

DEFAULT_MODE: Final[str] = "board"

AUTO_MODE_KEY: Final[str] = "auto"
"""自动组队入口（ADR-0042）：按问题从角色库选角并决定治理方式。

刻意不进 MODE_DEFINITIONS——后者是「固定角色静态目录」的单一事实源
（ADR-0040），auto 是动态机制，进入会破坏该前提。
"""

AUTO_MODE_HELP: Final[str] = "AI 根据问题自动挑选角色与协作方式（从角色库组队，无需手动选模式）"

AUTO_EXAMPLE_PROMPTS: Final[tuple[str, ...]] = (
    "给新功能写发布文案并评估技术风险",
    "制定季度产品路线图的关键里程碑",
    "从效率、协作、文化三个角度分析远程办公",
    "是否应在本周发布灰度版本？",
)

_MEMBER_MAX_STEPS = 8
_LEAD_MAX_STEPS = 20
_SOLO_MAX_STEPS = 12


def get_mode_definition(mode: str) -> ModeDefinition:
    if mode not in MODE_DEFINITIONS:
        raise KeyError(f"unknown mode {mode!r}")
    return MODE_DEFINITIONS[mode]


def max_steps_for_role(*, is_lead: bool, is_solo: bool) -> int:
    if is_solo:
        return _SOLO_MAX_STEPS
    if is_lead:
        return _LEAD_MAX_STEPS
    return _MEMBER_MAX_STEPS
