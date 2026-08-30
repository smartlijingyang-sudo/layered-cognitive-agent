"""TeamAwareness — lead 一次 run 期间对团队的实时认知（ADR-0035 / ADR-0036）。

统一取代上一代 ConsultationState / RoutingState 的分裂：consult/board 与
routing 的本质差异只是**有无咨询义务**，由可选的 ``ConsultDuty`` 组件表达——
不再有第二个会话类型，也不再有按类型窄化的分发。

- 有 ``consult_duty``（consult / board）：状态板是应答进度的权威视图，
  board 授权下由 ``MustConsultAllMembers`` 守门。
- 无 ``consult_duty``（routing）：``results`` 回报记录是事实源，支撑监督者
  提示词与幂等委派；没有全员应答不变量。

字段纪律由 contracts 纯净门禁（ADR-0015）与本文件的单一概念承担，
不再复活字段白名单断言看守裂缝。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lca.contracts.models.team.consultation import ConsultationOutcome
from lca.contracts.models.team.delegation import DelegationResult
from lca.contracts.models.team.member_status import MemberStatus
from lca.contracts.models.team.role_team import RoleProfile


@dataclass
class ConsultDuty:
    """咨询义务（consult / board）：进度板 + 证据账本 + 重试计数。

    正交两平面（ADR-0049）:
    - ``member_status``：控制面进度（还要不要问）
    - ``outcomes``：证据平面（综合时用什么）

    ``max_attempts`` 由组合期注入（唯一默认值见
    ``lca.contracts.protocols.journal.spec.DEFAULT_DELEGATE_MAX_ATTEMPTS``），
    契约层不私藏重试策略。

    Mutability（一次 run 内）:
    - 循环中变更: ``member_status``、``attempts``、``outcomes``
    - 注入后固定: ``max_attempts``、``min_usable_partial_chars``
    """

    member_status: MemberStatus
    max_attempts: int
    attempts: dict[str, int] = field(default_factory=dict)
    outcomes: list[ConsultationOutcome] = field(default_factory=list)
    min_usable_partial_chars: int = 80


@dataclass
class TeamAwareness:
    """Lead 一次 run 的团队实时认知：名册 + 委派回报记录 + 可选咨询义务。

    仅 lead run 持有；solo / member 的 awareness 槽为 None。
    - 自由 routing（无 consult_duty）：``results`` 是委派事实源
    - 义务路径：进度在状态板，证据在 ``consult_duty.outcomes``（ADR-0049）
    """

    teammates: list[RoleProfile] = field(default_factory=list)
    results: list[DelegationResult] = field(default_factory=list)
    consult_duty: ConsultDuty | None = None
    assigned_roles: list[str] = field(default_factory=list)
