"""委派结算跟踪 —— 结算落定后直接更新 TeamAwareness（ADR-0035）。

重试分类是纯函数；记账分路由 ``TeamAwareness.settlement`` 的有无决定：
有结算义务（consult / board）更新状态板，自由 routing 记入账本。
消费方不再按会话类型窄化——awareness 是唯一的具体类型。
"""

from __future__ import annotations

from lca.contracts.decision import DelegationSpec, Observation
from lca.contracts.delegation import DelegationResult
from lca.contracts.enums import RoleStatus
from lca.contracts.ids import new_id, utc_now
from lca.contracts.member_status import MemberStatus
from lca.contracts.semantic_keys import (
    FAILURE_KIND,
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_VALIDATION,
    OBS_TASK_ID,
)
from lca.contracts.state import AgentState
from lca.contracts.team_awareness import Settlement, TeamAwareness


def settlement_board(state: AgentState) -> MemberStatus | None:
    """当前 awareness 的必问成员状态板；无结算义务时为 None。"""
    awareness = state.team_awareness
    if awareness is None or awareness.settlement is None:
        return None
    return awareness.settlement.member_status


def _next_role_status(
    *,
    success: bool,
    failure_kind: str,
    attempts_after: int,
    max_attempts: int,
) -> RoleStatus:
    """Pure classifier: no AgentState/awareness access."""
    if success:
        return RoleStatus.DONE
    if failure_kind == FAILURE_KIND_VALIDATION:
        return RoleStatus.FAILED
    if attempts_after >= max_attempts:
        return RoleStatus.FAILED
    return RoleStatus.PENDING


def _settle_on_board(
    settlement: Settlement, spec: DelegationSpec, observation: Observation
) -> None:
    """更新结算状态板与重试计数（单个委派目标）。"""
    board = settlement.member_status
    role = spec.target_role
    if role is None or role not in board.required_roles:
        return

    if observation.success:
        settlement.member_status = board.mark(role, RoleStatus.DONE)
        return

    failure_kind = observation.extra.get(FAILURE_KIND, FAILURE_KIND_EXECUTION)
    attempts_after = settlement.attempts.get(role, 0) + 1
    settlement.attempts[role] = attempts_after

    new_status = _next_role_status(
        success=False,
        failure_kind=failure_kind,
        attempts_after=attempts_after,
        max_attempts=settlement.max_attempts,
    )
    settlement.member_status = board.mark(role, new_status)


def _record_in_ledger(
    awareness: TeamAwareness, spec: DelegationSpec, observation: Observation, step: int
) -> None:
    """软分配日志 + 事实账本追加。

    失败的结算也记录，提示词才能呈现「谁还没回复」；``find_result`` 只匹配成功项。
    """
    if not spec.target_role:
        return
    if spec.target_role not in awareness.assigned_roles:
        awareness.assigned_roles.append(spec.target_role)
    task_id = observation.extra.get(OBS_TASK_ID)
    output = observation.payload if observation.success else None
    awareness.results.append(
        DelegationResult(
            result_id=new_id("dres"),
            target_role=spec.target_role,
            subtask=spec.subtask,
            output=str(output) if output is not None else None,
            success=observation.success,
            error=observation.error,
            task_id=str(task_id) if task_id is not None else None,
            step=step,
            returned_at=utc_now(),
        )
    )


def settle_delegation(state: AgentState, spec: DelegationSpec, observation: Observation) -> None:
    """单个委派目标结算落定后，更新 lead 的团队 awareness。

    - 有结算义务（consult / board）：更新状态板与重试计数；
    - 自由 routing：记软分配日志并追加事实账本。
    solo / member（无 awareness）直接放行。
    """
    awareness = state.team_awareness
    if awareness is None:
        return
    if awareness.settlement is not None:
        _settle_on_board(awareness.settlement, spec, observation)
        return
    _record_in_ledger(awareness, spec, observation, state.step)
