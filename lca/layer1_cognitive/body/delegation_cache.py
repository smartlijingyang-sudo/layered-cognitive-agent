"""幂等委派 —— 路由账本的缓存命中短路与归属标签。

纯函数集：``DelegateOperation`` 只负责调度编排；账本匹配、缓存 span 发射与
Observation 归属标签集中在此，可独立测试。
"""

from __future__ import annotations

from lca.contracts.decision import DelegationSpec, Observation
from lca.contracts.delegation import find_result
from lca.contracts.enums import MemoryRecordKind
from lca.contracts.ids import new_id
from lca.contracts.semantic_keys import (
    OBS_CACHE_HIT,
    OBS_MEMBER_RESULTS,
    OBS_MEMBER_SUBTASKS,
    OBS_RESULT_KIND,
    OBS_TASK_ID,
)
from lca.contracts.state import AgentState
from lca.contracts.telemetry import (
    ATTR_CALLEE_ROLE,
    ATTR_STEP,
    ATTR_SUBTASK_PREVIEW,
    SpanName,
)
from lca.layer0_infra.observability import span
from lca.layer0_infra.observability.redaction import sanitize, truncate


def cached_delegation_observation(spec: DelegationSpec, state: AgentState) -> Observation | None:
    """幂等短路：账本中已有成功结算的 ``(target_role, subtask)`` 直接复用。

    账本只在自由 routing（无 settlement）下累积——settlement 路径由状态板
    管辖，不走此路径。命中时发射 ``delegate.cache_hit`` span，不产生
    transport 往返。语义刻意保守：仅拦字面重复，改写措辞的新问题不受影响。
    """
    awareness = state.team_awareness
    if awareness is None or not spec.target_role:
        return None
    hit = find_result(awareness.results, target_role=spec.target_role, subtask=spec.subtask)
    if hit is None:
        return None
    with span(
        SpanName.DELEGATE_CACHE_HIT,
        **{
            ATTR_CALLEE_ROLE: hit.target_role,
            ATTR_STEP: state.step,
            ATTR_SUBTASK_PREVIEW: truncate(sanitize(spec.subtask)),
        },
    ):
        pass
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
