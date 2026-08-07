"""自动组队契约 —— RoleLibrary / TeamCaster（ADR-0042）。

自动组队是声明式 TeamSpec 的另一个*生产者*：TeamCaster 把一句话目标变成
白名单校验过的 CastingPlan，组合翻译与手写构造走同一条 Agent/Team 路径，
不引入任何新的运行时机制。

角色库是纯数据内容包（Markdown + frontmatter），框架只持有 RoleLibrary
抽象，不假设存储形态。治理方式复用既有封闭词表（LeadMandate 值 +
Coordination 策略键），casting 不发明新的团队拓扑；Graph 暂未开放
（Phase 2，见 ADR-0042）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from lca.contracts.models.team.team_coordination import (
    STRATEGY_KEY_DEBATE,
    STRATEGY_KEY_FAN_OUT,
    STRATEGY_KEY_PEER_RELAY,
    STRATEGY_KEY_PEER_SWARM,
    STRATEGY_KEY_PIPELINE,
    LeadMandate,
)

if TYPE_CHECKING:
    from lca.contracts.protocols.infra import LLMAdapter


class CastingError(ValueError):
    """自动组队判定失败：LLM 输出解析/白名单校验/纠正重试全部失败。"""


class RoleNotFoundError(ValueError):
    """role_id 不存在于角色库。"""


LEAD_CASTING_KINDS: frozenset[str] = frozenset(mandate.value for mandate in LeadMandate)
"""可选的有主导者治理词表 —— 即 LeadMandate 的取值（routing/consult/board）。"""

COORDINATION_CASTING_KINDS: frozenset[str] = frozenset(
    (
        STRATEGY_KEY_PIPELINE,
        STRATEGY_KEY_FAN_OUT,
        STRATEGY_KEY_PEER_RELAY,
        STRATEGY_KEY_PEER_SWARM,
        STRATEGY_KEY_DEBATE,
    )
)
"""可选的无主导者治理词表 —— Coordination 策略键（graph 暂未开放）。"""

CASTING_GOVERNANCE_KINDS: frozenset[str] = LEAD_CASTING_KINDS | COORDINATION_CASTING_KINDS
"""casting 可选治理方式全集 —— 既有封闭词表，无新增拓扑概念（ADR-0030/0034）。"""

CASTING_MIN_ROLES = 2
"""一次组队的最少角色数：团队至少两名成员。"""

CASTING_MAX_ROLES = 6
"""一次组队的最多角色数：控制成本与协作开销。"""


@dataclass(frozen=True)
class RoleIndexEntry:
    """精简索引条目 —— 只进组队提示词，不含角色全文，控制 token 成本。"""

    role_id: str
    title: str
    department: str
    summary: str


@dataclass(frozen=True)
class RoleCard:
    """角色库里单个角色的完整声明式定义 —— 字段对齐 AgentSpec.profile。

    ``title`` → RoleProfile.role，``summary`` → RoleProfile.goal 的基底，
    ``backstory`` → RoleProfile.backstory（角色卡全文：身份/规则/流程/交付物）。
    """

    role_id: str
    title: str
    department: str
    summary: str
    backstory: str


@dataclass(frozen=True)
class SelectedRole:
    """一次选角中的单个角色：role_id + 可选的本次任务分工提示。"""

    role_id: str
    task_hint: str | None = None


@dataclass(frozen=True)
class CastingPlan:
    """一次 casting 的产物 —— 已过白名单校验，尚未编译成 TeamSpec。

    ``governance_kind`` 取值必须在 CASTING_GOVERNANCE_KINDS 内；lead 类
    （routing/consult/board）必须给出 ``lead_role_id`` 且它是 selected 之一。
    """

    selected: tuple[SelectedRole, ...]
    governance_kind: str
    lead_role_id: str | None = None
    rationale: str = ""


class RoleLibrary(Protocol):
    """角色库抽象：index() 供组队选角，get() 供组队后取全文。"""

    def index(self) -> tuple[RoleIndexEntry, ...]:
        """全部角色的精简索引（role_id 升序，保证确定性）。"""
        ...

    def get(self, role_id: str) -> RoleCard:
        """按 role_id 取完整角色卡；未知 id 抛 RoleNotFoundError。"""
        ...


class TeamCaster(Protocol):
    """选角抽象：把一句话目标变成白名单校验过的 CastingPlan。"""

    async def cast(self, objective: str, library: RoleLibrary, llm: LLMAdapter) -> CastingPlan:
        """为 objective 选角并决定治理方式；判定失败抛 CastingError。"""
        ...
