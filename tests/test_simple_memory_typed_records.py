"""记忆类型化写入 —— 观察按 kind 落盘，委派结果带归属。"""

from __future__ import annotations

import unittest

from lca.contracts.atoms.enums import MemoryLayer, MemoryRecordKind, ReflectionVerdict
from lca.contracts.atoms.semantic_keys import (
    META_ROLE,
    META_SUBTASK,
    OBS_MEMBER_RESULTS,
    OBS_MEMBER_SUBTASKS,
    OBS_RESULT_KIND,
)
from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.decision import Observation, Reflection
from lca.contracts.models.core.state import AgentState
from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem


def _state(step: int = 0) -> AgentState:
    return AgentState(trace_id="trace_1", task="probe", budget=create_budget(), step=step)


def _reflection() -> Reflection:
    return Reflection(reflection_id="ref_1", verdict=ReflectionVerdict.ON_TRACK)


class TestTypedWorkingMemory(unittest.IsolatedAsyncioTestCase):
    async def test_delegation_observation_writes_one_record_per_member(self) -> None:
        mem = SimpleMemorySystem()
        obs = Observation(
            observation_id="obs_1",
            success=True,
            payload={"Alice": "tech risk", "Bob": "biz risk"},
            extra={
                OBS_RESULT_KIND: MemoryRecordKind.DELEGATION_RESULT,
                OBS_MEMBER_RESULTS: {"Alice": "tech risk", "Bob": "biz risk"},
                OBS_MEMBER_SUBTASKS: {"Alice": "sub a", "Bob": "sub b"},
            },
        )
        await mem.update(_state(), obs, _reflection())
        working = mem.query(MemoryLayer.WORKING)
        self.assertEqual(len(working), 2)
        by_role = {r.metadata[META_ROLE]: r for r in working}
        self.assertEqual(by_role["Alice"].content, "tech risk")
        self.assertEqual(by_role["Alice"].metadata[META_SUBTASK], "sub a")
        self.assertEqual(by_role["Alice"].kind, MemoryRecordKind.DELEGATION_RESULT)
        self.assertEqual(by_role["Bob"].content, "biz risk")
        # 不再以 TOOL_RESULT 糊形式出现
        for record in working:
            self.assertNotIn("TOOL_RESULT", record.content)

    async def test_tool_result_keeps_prefix_and_kind(self) -> None:
        mem = SimpleMemorySystem()
        obs = Observation(
            observation_id="obs_2",
            success=True,
            payload="42",
            extra={OBS_RESULT_KIND: MemoryRecordKind.TOOL_RESULT},
        )
        await mem.update(_state(), obs, _reflection())
        working = mem.query(MemoryLayer.WORKING)
        self.assertEqual(len(working), 1)
        self.assertEqual(working[0].kind, MemoryRecordKind.TOOL_RESULT)
        self.assertTrue(working[0].content.startswith("TOOL_RESULT:"))

    async def test_respond_observation_records_own_reply(self) -> None:
        mem = SimpleMemorySystem()
        obs = Observation(
            observation_id="obs_3",
            success=True,
            payload="my final answer",
            extra={OBS_RESULT_KIND: MemoryRecordKind.RESPONSE},
        )
        await mem.update(_state(step=1), obs, _reflection())
        working = mem.query(MemoryLayer.WORKING)
        self.assertEqual(len(working), 1)
        self.assertEqual(working[0].kind, MemoryRecordKind.RESPONSE)
        self.assertIn("my final answer", working[0].content)
        self.assertNotIn("TOOL_RESULT", working[0].content)

    async def test_legacy_observation_falls_back_to_generic(self) -> None:
        mem = SimpleMemorySystem()
        obs = Observation(observation_id="obs_4", success=True, payload="raw")
        await mem.update(_state(), obs, _reflection())
        working = mem.query(MemoryLayer.WORKING)
        self.assertEqual(len(working), 1)
        self.assertEqual(working[0].kind, MemoryRecordKind.GENERIC)
        self.assertTrue(working[0].content.startswith("TOOL_RESULT:"))

    async def test_failed_observation_is_not_written_to_working(self) -> None:
        mem = SimpleMemorySystem()
        obs = Observation(observation_id="obs_5", success=False, payload="oops")
        await mem.update(_state(), obs, _reflection())
        self.assertEqual(mem.query(MemoryLayer.WORKING), [])


if __name__ == "__main__":
    unittest.main()
