"""委派回报跟踪 —— 进度板 + 证据账本（ADR-0035 / ADR-0036 / ADR-0049）。

重试分类是纯函数；登记路径按 ``TeamAwareness.consult_duty`` 的有无决定：
有咨询义务（consult / board）更新状态板与 outcomes；自由 routing 追加回报记录。
"""

from __future__ import annotations

from lca.contracts.atoms.enums import RoleStatus
from lca.contracts.atoms.ids import new_id, utc_now
from lca.contracts.atoms.semantic_keys import (
    COMPLETION_EMPTY,
    COMPLETION_FULL,
    COMPLETION_PARTIAL,
    FAILURE_KIND,
    FAILURE_KIND_TRANSIENT,
    FAILURE_KIND_VALIDATION,
    OBS_COMPLETION_QUALITY,
    OBS_DELEGATION_ID,
    OBS_TASK_ID,
)
from lca.contracts.models.core.budget import DEFAULT_MIN_USABLE_PARTIAL_CHARS
from lca.contracts.models.core.decision import DelegationSpec, Observation
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.team.consultation import (
    ConsultationDisposition,
    ConsultationOutcome,
)
from lca.contracts.models.team.delegation import DelegationResult
from lca.contracts.models.team.member_status import MemberStatus
from lca.contracts.models.team.team_awareness import ConsultDuty, TeamAwareness


def duty_board(state: AgentState) -> MemberStatus | None:
    """当前 awareness 的必问成员状态板；无咨询义务时为 None。"""
    awareness = state.team_awareness
    if awareness is None or awareness.consult_duty is None:
        return None
    return awareness.consult_duty.member_status


def duty_consult(state: AgentState) -> ConsultDuty | None:
    """当前 awareness 的咨询义务；无则 None。"""
    awareness = state.team_awareness
    if awareness is None:
        return None
    return awareness.consult_duty


def _evidence_text(observation: Observation) -> str | None:
    payload = observation.payload
    if payload is None:
        return None
    text = payload if isinstance(payload, str) else str(payload)
    text = text.strip()
    return text or None


def _completion_quality(observation: Observation) -> str:
    raw = observation.extra.get(OBS_COMPLETION_QUALITY)
    if isinstance(raw, str) and raw:
        return raw
    if observation.success:
        return COMPLETION_FULL
    if _evidence_text(observation):
        return COMPLETION_PARTIAL
    return COMPLETION_EMPTY


def _disposition_for(observation: Observation, *, quality: str) -> ConsultationDisposition:
    failure_kind = str(observation.extra.get(FAILURE_KIND) or "")
    if observation.success and quality == COMPLETION_FULL:
        return ConsultationDisposition.COMPLETED
    if quality == COMPLETION_PARTIAL:
        return ConsultationDisposition.PARTIAL
    if failure_kind == FAILURE_KIND_VALIDATION:
        return ConsultationDisposition.VALIDATION_FAILED
    if failure_kind == FAILURE_KIND_TRANSIENT or (
        observation.error and "超时" in observation.error
    ):
        return ConsultationDisposition.TIMEOUT
    if observation.success:
        return ConsultationDisposition.COMPLETED
    return ConsultationDisposition.ERROR


def _usable(
    evidence: str | None,
    disposition: ConsultationDisposition,
    min_chars: int,
) -> bool:
    if disposition == ConsultationDisposition.COMPLETED:
        return bool(evidence)
    if disposition == ConsultationDisposition.PARTIAL:
        return bool(evidence) and len(evidence or "") >= min_chars
    return False


def _next_role_status(
    *,
    disposition: ConsultationDisposition,
    usable: bool,
    attempts_after: int,
    max_attempts: int,
) -> RoleStatus:
    if disposition == ConsultationDisposition.COMPLETED and usable:
        return RoleStatus.DONE
    if disposition == ConsultationDisposition.PARTIAL and usable:
        return RoleStatus.DONE_PARTIAL
    if disposition == ConsultationDisposition.VALIDATION_FAILED:
        return RoleStatus.FAILED
    if attempts_after >= max_attempts:
        return RoleStatus.FAILED
    # empty timeout / error → 仍可重试
    return RoleStatus.PENDING


def _append_outcome(
    duty: ConsultDuty,
    spec: DelegationSpec,
    observation: Observation,
    *,
    step: int,
) -> ConsultationOutcome:
    role = spec.target_role or ""
    attempts_after = duty.attempts.get(role, 0) + 1
    duty.attempts[role] = attempts_after
    quality = _completion_quality(observation)
    evidence = _evidence_text(observation)
    disposition = _disposition_for(observation, quality=quality)
    min_chars = duty.min_usable_partial_chars or DEFAULT_MIN_USABLE_PARTIAL_CHARS
    usable = _usable(evidence, disposition, min_chars)
    failure_kind = observation.extra.get(FAILURE_KIND)
    outcome = ConsultationOutcome(
        outcome_id=new_id("cout"),
        role=role,
        attempt=attempts_after,
        disposition=disposition,
        evidence=evidence,
        usable=usable,
        failure_kind=str(failure_kind) if failure_kind is not None else None,
        task_id=(
            str(observation.extra.get(OBS_TASK_ID))
            if observation.extra.get(OBS_TASK_ID) is not None
            else None
        ),
        delegation_id=(
            str(observation.extra.get(OBS_DELEGATION_ID))
            if observation.extra.get(OBS_DELEGATION_ID) is not None
            else None
        ),
        step=step,
        returned_at=utc_now(),
        subtask=spec.subtask,
        error=observation.error,
        latency_ms=observation.latency_ms,
    )
    duty.outcomes.append(outcome)
    return outcome


def _record_report(
    awareness: TeamAwareness, spec: DelegationSpec, observation: Observation, step: int
) -> None:
    """软分配日志 + 回报记录追加。

    失败的回报也记录，提示词才能呈现「谁还没回复」；``find_result`` 只匹配成功项。
    超时 partial：output 保留 evidence，success 仍为 False（幂等不误命中）。
    """
    if not spec.target_role:
        return
    if spec.target_role not in awareness.assigned_roles:
        awareness.assigned_roles.append(spec.target_role)
    task_id = observation.extra.get(OBS_TASK_ID)
    evidence = _evidence_text(observation)
    output = evidence if (observation.success or evidence) else None
    awareness.results.append(
        DelegationResult(
            result_id=new_id("dres"),
            target_role=spec.target_role,
            subtask=spec.subtask,
            output=output,
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

    - 有咨询义务（consult / board）：更新状态板 + outcomes 证据账本；
    - 自由 routing：记软分配日志并追加回报记录。
    solo / member（无 awareness）直接放行。
    """
    awareness = state.team_awareness
    if awareness is None:
        return
    if awareness.consult_duty is not None:
        duty = awareness.consult_duty
        board = duty.member_status
        role = spec.target_role
        if role is None or role not in board.required_roles:
            return
        outcome = _append_outcome(duty, spec, observation, step=state.step)
        attempts_after = duty.attempts.get(role, 0)
        new_status = _next_role_status(
            disposition=outcome.disposition,
            usable=outcome.usable,
            attempts_after=attempts_after,
            max_attempts=duty.max_attempts,
        )
        duty.member_status = board.mark(role, new_status)
        return
    _record_report(awareness, spec, observation, state.step)
