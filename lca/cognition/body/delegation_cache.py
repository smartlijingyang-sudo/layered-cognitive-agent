"""幂等委派 —— 回报记录的缓存命中短路与归属标签。

纯函数集：``DelegateOperation`` 只负责调度编排；回报记录匹配、缓存 span 发射与
Observation 归属标签集中在此，可独立测试。
"""

from __future__ import annotations

from lca.contracts.atoms.enums import MemoryRecordKind
from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import (
    OBS_CACHE_HIT,
    OBS_MEMBER_RESULTS,
    OBS_MEMBER_SUBTASKS,
    OBS_RESULT_KIND,
    OBS_TASK_ID,
)
from lca.contracts.models.core.decision import DelegationSpec, Observation
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.observability.journal import DelegationCacheHit
from lca.contracts.models.team.delegation import find_result
from lca.infrastructure.observability import record


def cached_delegation_observation(spec: DelegationSpec, state: AgentState) -> Observation | None:
    """幂等短路：回报记录中已有成功返回的 ``(target_role, subtask)`` 直接复用。

    回报记录只在自由 routing（无 consult_duty）下累积——义务路径由状态板
    管辖，不走此路径。命中时 record ``DelegationCacheHit``，不产生
    transport 往返。语义刻意保守：仅拦字面重复，改写措辞的新问题不受影响。
    """
    awareness = state.team_awareness
    if awareness is None or not spec.target_role:
        return None
    hit = find_result(awareness.results, target_role=spec.target_role, subtask=spec.subtask)
    if hit is None:
        return None
    record(
        DelegationCacheHit(
            callee_role=hit.target_role,
            subtask_preview=spec.subtask,
            step=state.step,
        )
    )
    observation = Observation(
        observation_id=new_id("obs"),
        success=True,
        payload=hit.output,
        extra={OBS_TASK_ID: hit.task_id or "", OBS_CACHE_HIT: True},
    )
    return tag_delegation_extra(observation, spec)


def tag_delegation_extra(observation: Observation, spec: DelegationSpec) -> Observation:
    """统一附委派归属（kind + role→result/subtask 映射），记忆侧据此写类型化记录。"""
    extra = dict(observation.extra or {})
    extra.setdefault(OBS_RESULT_KIND, MemoryRecordKind.DELEGATION_RESULT)
    if OBS_MEMBER_RESULTS not in extra:
        key = spec.target_role or spec.target_agent_id or observation.observation_id
        extra[OBS_MEMBER_RESULTS] = {
            str(key): observation.payload if observation.success else observation.error
        }
        extra[OBS_MEMBER_SUBTASKS] = {str(key): spec.subtask}
    observation.extra = extra
    return observation
