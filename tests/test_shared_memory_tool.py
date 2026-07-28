"""SharedMemoryTool + Turn history 契约测试（ADR-0016）。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.decision import Observation, Reflection, StructuredDecision
from lca.contracts.state import Budget, TypedState
from lca.contracts.types import TeamAssignment, Turn
from lca.layer1_cognitive.memory.team_shared_memory import TeamSharedMemoryStore
from lca.layer3_agent.shared_memory.shared_memory_tool import SharedMemoryTool


class TestSharedMemoryTool(unittest.IsolatedAsyncioTestCase):
    async def test_write_then_read_across_instances(self) -> None:
        store = TeamSharedMemoryStore(["semantic"])
        writer = SharedMemoryTool(store, team_id="team-1")
        reader = SharedMemoryTool(store, team_id="team-1")

        write_obs = await writer.execute(
            {"op": "write", "layer": "semantic", "content": "research notes about X"}
        )
        self.assertTrue(write_obs.success)

        read_obs = await reader.execute({"op": "read", "layer": "semantic"})
        self.assertTrue(read_obs.success)
        self.assertIn("research notes about X", read_obs.payload)

    async def test_validate_rejects_private_layer(self) -> None:
        store = TeamSharedMemoryStore(["semantic"])
        tool = SharedMemoryTool(store, team_id="team-1")
        obs = await tool.execute({"op": "read", "layer": "episodic"})
        self.assertFalse(obs.success)
        self.assertIn("未配置为共享", obs.error or "")

    async def test_list_op(self) -> None:
        store = TeamSharedMemoryStore(["semantic"])
        tool = SharedMemoryTool(store, team_id="t")
        await tool.execute({"op": "write", "content": "a"})
        await tool.execute({"op": "write", "content": "b"})
        obs = await tool.execute({"op": "list"})
        self.assertTrue(obs.success)
        self.assertEqual(obs.payload["count"], 2)


class TestTurnAndTeamAssignment(unittest.TestCase):
    def test_turn_on_typed_state_history(self) -> None:
        state = TypedState(trace_id="t1", task="demo", budget=Budget())
        decision = StructuredDecision(
            decision_id="d1",
            action_type="respond",
            rationale="r",
            confidence=0.9,
            response_text="hi",
        )
        obs = Observation(observation_id="o1", success=True, payload="hi")
        ref = Reflection(reflection_id="r1", verdict="on_track")
        state.history.append(Turn(decision=decision, observation=obs, reflection=ref))
        self.assertEqual(len(state.history), 1)
        self.assertEqual(state.history[0].decision.action_type, "respond")

    def test_team_assignment_distinct_from_subtask_fields(self) -> None:
        assignment = TeamAssignment(
            member_id="researcher",
            objective="收集资料",
            depends_on=[],
        )
        self.assertEqual(assignment.member_id, "researcher")
        self.assertEqual(assignment.depends_on, [])


if __name__ == "__main__":
    unittest.main()
