"""委派回报跟踪 —— 成员返回落定后直接更新 TeamAwareness（ADR-0035 / ADR-0036）。

重试分类是纯函数；登记路径按 ``TeamAwareness.consult_duty`` 的有无决定：
有咨询义务（consult / board）更新状态板，自由 routing 追加回报记录。
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
from lca.contracts.team_awareness import ConsultDuty, TeamAwareness


def duty_board(state: AgentState) -> MemberStatus | None:
    """当前 awareness 的必问成员状态板；无咨询义务时为 None。"""
    awareness = state.team_awareness
    if awareness is None or awareness.consult_duty is None:
        return None
    return awareness.consult_duty.member_status


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


def _mark_on_board(duty: ConsultDuty, spec: DelegationSpec, observation: Observation) -> None:
    """更新咨询义务状态板与重试计数（单个委派目标）。"""
    board = duty.member_status
    role = spec.target_role
    if role is None or role not in board.required_roles:
        return

    if observation.success:
        duty.member_status = board.mark(role, RoleStatus.DONE)
        return

    failure_kind = observation.extra.get(FAILURE_KIND, FAILURE_KIND_EXECUTION)
    attempts_after = duty.attempts.get(role, 0) + 1
    duty.attempts[role] = attempts_after

    new_status = _next_role_status(
        success=False,
        failure_kind=failure_kind,
        attempts_after=attempts_after,
        max_attempts=duty.max_attempts,
    )
    duty.member_status = board.mark(role, new_status)


def _record_report(
    awareness: TeamAwareness, spec: DelegationSpec, observation: Observation, step: int
) -> None:
    """软分配日志 + 回报记录追加。

    失败的回报也记录，提示词才能呈现「谁还没回复」；``find_result`` 只匹配成功项。
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


def record_delegation_return(
    state: AgentState, spec: DelegationSpec, observation: Observation
) -> None:
    """单个委派目标的回报落定后，更新 lead 的团队 awareness。

    - 有咨询义务（consult / board）：更新状态板与重试计数；
    - 自由 routing：记软分配日志并追加回报记录。
    solo / member（无 awareness）直接放行。
    """
    awareness = state.team_awareness
    if awareness is None:
        return
    if awareness.consult_duty is not None:
        _mark_on_board(awareness.consult_duty, spec, observation)
        return
    _record_report(awareness, spec, observation, state.step)
