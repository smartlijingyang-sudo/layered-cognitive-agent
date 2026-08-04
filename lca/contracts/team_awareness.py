"""TeamAwareness — lead 一次 run 期间对团队的实时认知（ADR-0035）。

统一取代上一代 ConsultationState / RoutingState 的分裂：consult/board 与
routing 的本质差异只是**有无结算义务**，由可选的 ``Settlement`` 组件表达——
不再有第二个会话类型，也不再有按类型窄化的分发。

- 有 ``settlement``（consult / board）：状态板是结算进度的权威视图，
  board 授权下由 ``MustConsultAllMembers`` 守门。
- 无 ``settlement``（routing）：``results`` 账本是事实源，支撑监督者提示词
  与幂等委派；没有全员结算不变量。

字段纪律由 contracts 纯净门禁（ADR-0015）与本文件的单一概念承担，
不再复活字段白名单断言看守裂缝。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lca.contracts.delegation import DelegationResult
from lca.contracts.member_status import MemberStatus
from lca.contracts.role_team import RoleProfile


@dataclass
class Settlement:
    """结算义务（consult / board 授权专属）：必问成员状态板 + 委派重试计数。

    ``max_attempts`` 由组合期注入（唯一默认值见
    ``lca.contracts.agent_spec.DEFAULT_DELEGATE_MAX_ATTEMPTS``），
    契约层不私藏重试策略。

    Mutability（一次 run 内）:
    - 循环中变更: ``member_status``（整体替换）、``attempts``
    - 注入后固定: ``max_attempts``
    """

    member_status: MemberStatus
    max_attempts: int
    attempts: dict[str, int] = field(default_factory=dict)


@dataclass
class TeamAwareness:
    """Lead 一次 run 的团队实时认知：名册 + 委派账本 + 可选结算义务。

    仅 lead run 持有；solo / member 的 awareness 槽为 None。
    ``results`` 只在自由 routing（无 settlement）下累积——settlement 路径的
    结算进度由状态板表达，账本不参与，避免双份事实源。
    """

    teammates: list[RoleProfile] = field(default_factory=list)
    results: list[DelegationResult] = field(default_factory=list)
    settlement: Settlement | None = None
    assigned_roles: list[str] = field(default_factory=list)
    notes: str = ""
