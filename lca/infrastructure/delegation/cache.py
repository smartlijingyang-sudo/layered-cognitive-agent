"""Delegation cache hit short-circuit — infrastructure seam (ADR-0194 P1-16).

Cognition body calls :func:`cached_delegation_observation` / :func:`tag_delegation_extra`
here; ``team.delegation.cache_hit`` commits via ``delegation_journal_commit``.
Plugin ``DelegationCachePlugin`` delegates to this module for shared semantics.

Commit seam (RA-012): the cache-hit commit path — spine fact via
``lca.loop.commit.delegation_journal`` plus journal ``DelegationCacheHit`` via
``lca.infrastructure.observability.record``, gated on a bound raw session — is an
explicit :class:`CacheHitCommit` parameter on :func:`cached_delegation_observation`,
defaulting to the module-level :func:`_default_commit_hit` wiring. The
loop/session/observability imports live at module level (spike-proven acyclic on
2026-10-07: fresh-interpreter imports pass in every order, so no import cycle was
ever dodged here), keeping the layer edges honest; tests inject a fake through the
parameter instead of reaching into the loop/session layers.
"""

from __future__ import annotations

from typing import Protocol

from lca.contracts.atoms.enums.enums import MemoryRecordKind
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import (
    OBS_CACHE_HIT,
    OBS_MEMBER_RESULTS,
    OBS_MEMBER_SUBTASKS,
    OBS_RESULT_KIND,
    OBS_TASK_ID,
)
from lca.contracts.models.core.execution.decision import DelegationSpec, Observation
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.models.observability.journal.journal import DelegationCacheHit
from lca.contracts.models.team.delegation.delegation import find_result
from lca.infrastructure.observability import record
from lca.infrastructure.session.bindings import (
    active_publish_session,
    resolve_raw_session,
)
from lca.loop.commit.delegation_journal import commit_delegation_cache_hit


class CacheHitCommit(Protocol):
    """Commit seam for a delegation cache hit (RA-012).

    Carries the dual emission — ``team.delegation.cache_hit`` spine fact plus
    journal ``DelegationCacheHit`` — so the commit path is testable through the
    :func:`cached_delegation_observation` interface. Production uses
    :func:`_default_commit_hit`; tests inject a fake.
    """

    def __call__(
        self, *, callee_role: str, subtask: str, step: int, state: AgentState
    ) -> None: ...


def _default_commit_hit(
    *, callee_role: str, subtask: str, step: int, state: AgentState
) -> None:
    """Ambient commit wiring: spine fact + journal, semantics unchanged (RA-012)."""

    commit_delegation_cache_hit(
        callee_role=callee_role,
        subtask=subtask,
        step=step,
        state=state,
    )
    # journal 真值：幂等短路是协作叙事的一等公民事件，与 spine fact 同点发射。
    # 热路径 cheap 检查（todo-38，2026-10-05 裁决）：无可写 journal 的 raw
    # Session 时跳过，不抛 RuntimeError（record 内部 resolve_raw_session
    # 为 None 即 fail-loud；v2 事件面的 FakeSession 不满足 journal 写面）。
    if resolve_raw_session(active_publish_session()) is not None:
        record(
            DelegationCacheHit(
                callee_role=callee_role,
                subtask_preview=subtask,
                step=step,
            )
        )


def cached_delegation_observation(
    spec: DelegationSpec,
    state: AgentState,
    *,
    commit: CacheHitCommit = _default_commit_hit,
) -> Observation | None:
    """幂等短路：回报记录中已有成功返回的 ``(target_role, subtask)`` 直接复用。

    命中时发 ``team.delegation.cache_hit`` v2 Event，同时 record journal
    ``DelegationCacheHit``（ADR-0037 Stage 6：delegate.cache_hit 词表改判
    EVENT，由 journal 事件承载）；不产生 transport 往返。
    语义保守：仅拦字面重复，改写措辞的新问题不受影响。

    ``commit`` 是显式接缝（RA-012）：默认走 :func:`_default_commit_hit` 的
    ambient 接线；测试可注入 fake 钉住调用契约而不碰 loop/session 层。
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
    commit(
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


__all__ = ["CacheHitCommit", "cached_delegation_observation", "tag_delegation_extra"]
