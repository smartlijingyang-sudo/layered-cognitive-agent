"""SharedMemory + Turn history 契约测试。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.cognition.memory.simple_memory import SimpleMemorySystem
from lca.cognition.memory.team_shared_memory import TeamSharedMemoryStore
from lca.contracts.atoms.enums import MemoryLayer
from lca.contracts.models.core.decision import Decision, Observation, Reflection, Turn
from lca.contracts.models.core.memory import MemoryRecord
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.team.team_coordination import TeamAssignment


class TestSharedMemorySinglePath(unittest.IsolatedAsyncioTestCase):
    """共享记忆通过 MemorySystem 单路径访问（HasSharedMemory）。"""

    async def test_shared_write_visible_across_agents(self) -> None:
        store = TeamSharedMemoryStore([MemoryLayer.SEMANTIC])
        agent_a = SimpleMemorySystem()
        agent_b = SimpleMemorySystem()
        agent_a = SimpleMemorySystem(shared_store=store)  # was bind
        agent_b = SimpleMemorySystem(shared_store=store)  # was bind

        agent_a.write_shared_record(
            MemoryLayer.SEMANTIC,
            MemoryRecord(
                record_id="m1",
                content="research notes about X",
                memory_type=MemoryLayer.SEMANTIC,
                importance=0.8,
                source_trace_id="team-1",
            ),
        )

        results = agent_b.query(MemoryLayer.SEMANTIC)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].content, "research notes about X")

    async def test_query_private_layer(self) -> None:
        mem = SimpleMemorySystem()
        results = mem.query(MemoryLayer.WORKING)
        self.assertEqual(results, [])

    async def test_query_shared_layer_returns_empty_initially(self) -> None:
        store = TeamSharedMemoryStore([MemoryLayer.SEMANTIC])
        mem = SimpleMemorySystem(shared_store=store)
        self.assertEqual(mem.query(MemoryLayer.SEMANTIC), [])


class TestTurnAndTeamAssignment(unittest.TestCase):
    def test_turn_on_typed_state_history(self) -> None:
        state = AgentState(trace_id="t1", task="demo", budget=Budget())
        decision = Decision(
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
