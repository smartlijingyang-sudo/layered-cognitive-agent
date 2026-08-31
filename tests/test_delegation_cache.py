"""委派幂等短路与归属标签 —— delegation_cache 纯函数。"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from lca.cognition.body.delegation_cache import (
    cached_delegation_observation,
    tag_delegation_extra,
)
from lca.contracts.atoms.enums import MemoryRecordKind
from lca.contracts.atoms.semantic_keys import (
    OBS_CACHE_HIT,
    OBS_MEMBER_RESULTS,
    OBS_MEMBER_SUBTASKS,
    OBS_RESULT_KIND,
)
from lca.contracts.models.core.decision import DelegationSpec, Observation
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.team.delegation import DelegationResult
from lca.contracts.models.team.team_awareness import TeamAwareness


def _delegation_result(role: str = "Alice", subtask: str = "analyze") -> DelegationResult:
    return DelegationResult(
        result_id="dres_1",
        target_role=role,
        subtask=subtask,
        output="cached answer",
        success=True,
        error=None,
        task_id="task_9",
        step=0,
        returned_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
    )


def _state(awareness: TeamAwareness | None) -> AgentState:
    return AgentState(trace_id="t", task="probe", budget=Budget(), team_awareness=awareness)


class TestCachedDelegationObservation(unittest.TestCase):
    def test_hit_returns_cached_payload_without_transport(self) -> None:
        awareness = TeamAwareness(results=[_delegation_result()])
        spec = DelegationSpec(subtask="analyze", target_role="Alice")
        obs = cached_delegation_observation(spec, _state(awareness))
        assert obs is not None
        self.assertTrue(obs.success)
        self.assertEqual(obs.payload, "cached answer")
        self.assertTrue(obs.extra[OBS_CACHE_HIT])
        self.assertEqual(obs.extra[OBS_RESULT_KIND], MemoryRecordKind.DELEGATION_RESULT)
        self.assertEqual(obs.extra[OBS_MEMBER_RESULTS], {"Alice": "cached answer"})
        self.assertEqual(obs.extra[OBS_MEMBER_SUBTASKS], {"Alice": "analyze"})

    def test_miss_on_new_subtask(self) -> None:
        awareness = TeamAwareness(results=[_delegation_result()])
        spec = DelegationSpec(subtask="re-analyze with new angle", target_role="Alice")
        self.assertIsNone(cached_delegation_observation(spec, _state(awareness)))

    def test_miss_without_team_awareness(self) -> None:
        spec = DelegationSpec(subtask="analyze", target_role="Alice")
        self.assertIsNone(cached_delegation_observation(spec, _state(None)))

    def test_miss_without_target_role(self) -> None:
        awareness = TeamAwareness(results=[_delegation_result()])
        spec = DelegationSpec(subtask="analyze", target_agent_id="agent_x")
        self.assertIsNone(cached_delegation_observation(spec, _state(awareness)))


class TestTagDelegationExtra(unittest.TestCase):
    def test_tag_single_member_observation(self) -> None:
        spec = DelegationSpec(subtask="sub", target_role="Bob")
        obs = Observation(observation_id="obs_1", success=True, payload="bob output")
        tagged = tag_delegation_extra(obs, spec)
        self.assertEqual(tagged.extra[OBS_RESULT_KIND], MemoryRecordKind.DELEGATION_RESULT)
        self.assertEqual(tagged.extra[OBS_MEMBER_RESULTS], {"Bob": "bob output"})
        self.assertEqual(tagged.extra[OBS_MEMBER_SUBTASKS], {"Bob": "sub"})

    def test_existing_member_results_are_kept(self) -> None:
        spec = DelegationSpec(subtask="sub", target_role="Bob")
        obs = Observation(
            observation_id="obs_1",
            success=True,
            payload={"Bob": "agg"},
            extra={OBS_MEMBER_RESULTS: {"Bob": "agg"}},
        )
        tagged = tag_delegation_extra(obs, spec)
        self.assertEqual(tagged.extra[OBS_MEMBER_RESULTS], {"Bob": "agg"})
        self.assertNotIn(OBS_MEMBER_SUBTASKS, tagged.extra)


if __name__ == "__main__":
    unittest.main()
