"""Delegation cache hit short-circuit — infrastructure seam (ADR-0194 P1-16).

Cognition body calls :func:`cached_delegation_observation` / :func:`tag_delegation_extra`
here; ``team.delegation.cache_hit`` commits via ``delegation_journal_commit``.
Plugin ``DelegationCachePlugin`` delegates to this module for shared semantics.
"""

from __future__ import annotations

from lca.contracts.atoms.enums.enums import MemoryRecordKind
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.semantic_keys import (
    OBS_CACHE_HIT,
    OBS_MEMBER_RESULTS,
    OBS_MEMBER_SUBTASKS,
    OBS_RESULT_KIND,
    OBS_TASK_ID,
)
from lca.contracts.models.core.execution.decision import DelegationSpec, Observation
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.models.team.delegation.delegation import find_result


def cached_delegation_observation(spec: DelegationSpec, state: AgentState) -> Observation | None:
    """幂等短路：回报记录中已有成功返回的 ``(target_role, subtask)`` 直接复用。

    命中时发 ``team.delegation.cache_hit`` v2 Event；不产生 transport 往返。
    语义保守：仅拦字面重复，改写措辞的新问题不受影响。
    """
    awareness = state.team_awareness
    if awareness is None or not spec.target_role:
        return None
    hit = find_result(
        awareness.results,
        target_role=spec.target_role,
        subtask=spec.subtask,
    )
    if hit is None:
        return None
    from lca.loop.commit.delegation_journal import commit_delegation_cache_hit

    commit_delegation_cache_hit(
        callee_role=hit.target_role,
        subtask=spec.subtask,
        step=state.step,
        state=state,
    )
    observation = Observation(
        observation_id=new_id("obs"),
        success=True,
        payload=hit.output,
        extra={OBS_TASK_ID: hit.task_id or "", OBS_CACHE_HIT: True},
    )
    return tag_delegation_extra(observation, spec)


def tag_delegation_extra(observation: Observation, spec: DelegationSpec) -> Observation:
    """附委派归属（kind + role→result/subtask 映射）。"""
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


__all__ = ["cached_delegation_observation", "tag_delegation_extra"]
