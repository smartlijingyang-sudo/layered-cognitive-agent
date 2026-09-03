"""业务方 plugin: DelegationCachePlugin（ADR-0180 / ADR-0183 PR-7）。

ADR-0180 要求"一切都是插件"——业务方也是 plugin。
本 plugin 由 :mod:`lca_kernel.events.manifest` 通过 Manifest 装载；机制按
yaml SSOT 鉴权 ``publishers: [delegation_cache]`` 白名单。

调用方（cognition）通过 :func:`cached_delegation_observation` 兼容壳委托到本 plugin。
"""

from __future__ import annotations

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
from lca.contracts.models.team.delegation import find_result
from lca_kernel.events import TeamDelegationCacheHit
from lca_kernel.events.bus import EventBus

# 业务方 plugin id（与 yaml publishers 白名单一致）。
PUBLISHER_PLUGIN_ID = "delegation_cache"


class DelegationCachePlugin:
    """delegation_cache publisher plugin 实现。

    试点：单例模式（无状态）；profile 装载时由 manifest setup 构造一次。
    """

    def cached_observation(self, spec: DelegationSpec, state: AgentState) -> Observation | None:
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
        # 业务方一行发送入口（ADR-0183 §3.1）：构造 typed payload；EventBus 按 yaml 鉴权。
        EventBus.default().publish(
            TeamDelegationCacheHit(
                callee_role=hit.target_role,
                subtask=spec.subtask,
                step=state.step,
            ),
            producer=DelegationCachePlugin,
        )
        observation = Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=hit.output,
            extra={OBS_TASK_ID: hit.task_id or "", OBS_CACHE_HIT: True},
        )
        return self._tag_extra(observation, spec)

    @staticmethod
    def _tag_extra(observation: Observation, spec: DelegationSpec) -> Observation:
        """统一附委派归属（kind + role→result/subtask 映射）。"""
        from lca.contracts.atoms.enums import MemoryRecordKind

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


__all__ = ["PUBLISHER_PLUGIN_ID", "DelegationCachePlugin"]
