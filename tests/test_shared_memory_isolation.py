"""共享记忆隔离性测试 —— 正反两方向保证：

1. 未声明共享的团队，两个成员的 semantic memory 互不可见（防泄漏）。
2. 声明了共享的层确实互相可见（功能正确）。
3. episodic/working 层即使在共享模式下也保持私有（CoALA 语义边界）。
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.decision import Observation, Reflection
from lca.contracts.enums import MemoryLayer, ReflectionVerdict
from lca.contracts.memory import MemoryRecord
from lca.contracts.state import AgentState, Budget
from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem
from lca.layer1_cognitive.memory.team_shared_memory import TeamSharedMemoryStore


def _make_state(trace_id: str = "trace-1") -> AgentState:
    return AgentState(trace_id=trace_id, task="test", budget=Budget())


def _make_observation(success: bool = True, payload: str = "ok") -> Observation:
    return Observation(observation_id="obs-1", success=success, payload=payload)


def _make_reflection(verdict: ReflectionVerdict = ReflectionVerdict.ON_TRACK) -> Reflection:
    return Reflection(
        reflection_id="ref-1",
        verdict=verdict,
        lesson="test",
    )


def _make_semantic_record(content: str, trace_id: str = "trace-1") -> MemoryRecord:
    return MemoryRecord(
        record_id=f"mem-{content}",
        content=content,
        memory_type=MemoryLayer.SEMANTIC,
        importance=0.8,
        source_trace_id=trace_id,
    )


class TestTeamSharedMemoryStoreValidation(unittest.TestCase):
    """TeamSharedMemoryStore 构造参数校验。"""

    def test_valid_layers_accepted(self) -> None:
        store = TeamSharedMemoryStore([MemoryLayer.SEMANTIC, MemoryLayer.PROCEDURAL])
        self.assertEqual(set(store.shared_layers), {MemoryLayer.SEMANTIC, MemoryLayer.PROCEDURAL})

    def test_single_layer_accepted(self) -> None:
        store = TeamSharedMemoryStore([MemoryLayer.SEMANTIC])
        self.assertTrue(store.is_shared(MemoryLayer.SEMANTIC))
        self.assertFalse(store.is_shared(MemoryLayer.PROCEDURAL))

    def test_invalid_layer_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            TeamSharedMemoryStore([MemoryLayer.EPISODIC])
        self.assertIn("semantic/procedural", str(ctx.exception))

    def test_empty_layers_accepted(self) -> None:
        store = TeamSharedMemoryStore([])
        self.assertEqual(store.shared_layers, [])

    def test_add_to_unshared_layer_raises(self) -> None:
        store = TeamSharedMemoryStore([MemoryLayer.SEMANTIC])
        with self.assertRaises(KeyError):
            store.add_record(MemoryLayer.PROCEDURAL, _make_semantic_record("x"))


class TestSharedMemoryIsolation(unittest.IsolatedAsyncioTestCase):
    """未声明共享时，两个成员的 semantic memory 互不可见。"""

    async def test_private_semantic_not_visible_across_members(self) -> None:
        mem_a = SimpleMemorySystem()
        mem_b = SimpleMemorySystem()

        # 直接向私有层写入（模拟不共享场景）
        record = _make_semantic_record("agent-a-private-knowledge")
        mem_a._private_layers[MemoryLayer.SEMANTIC].append(record)

        state_a = await mem_a.perceive(_make_state("trace-a"))
        state_b = await mem_b.perceive(_make_state("trace-b"))

        a_contents = [r.content for r in state_a.retrieved_context]
        b_contents = [r.content for r in state_b.retrieved_context]

        self.assertIn("agent-a-private-knowledge", a_contents)
        self.assertNotIn("agent-a-private-knowledge", b_contents)


class TestSharedMemoryVisibility(unittest.IsolatedAsyncioTestCase):
    """声明共享后，共享层的记录在成员间互相可见。"""

    async def test_shared_semantic_visible_across_members(self) -> None:
        store = TeamSharedMemoryStore([MemoryLayer.SEMANTIC])
        mem_a = SimpleMemorySystem()
        mem_b = SimpleMemorySystem()
        mem_a = SimpleMemorySystem(shared_store=store)  # was bind
        mem_b = SimpleMemorySystem(shared_store=store)  # was bind

        record = _make_semantic_record("shared-knowledge")
        mem_a.write_shared_record(MemoryLayer.SEMANTIC, record)

        state_b = await mem_b.perceive(_make_state())
        b_contents = [r.content for r in state_b.retrieved_context]
        self.assertIn("shared-knowledge", b_contents)

    async def test_shared_procedural_visible_across_members(self) -> None:
        store = TeamSharedMemoryStore([MemoryLayer.PROCEDURAL])
        mem_a = SimpleMemorySystem()
        mem_b = SimpleMemorySystem()
        mem_a = SimpleMemorySystem(shared_store=store)  # was bind
        mem_b = SimpleMemorySystem(shared_store=store)  # was bind

        record = MemoryRecord(
            record_id="proc-1",
            content="shared-skill: use_tool",
            memory_type=MemoryLayer.PROCEDURAL,
            importance=0.7,
        )
        mem_a.write_shared_record(MemoryLayer.PROCEDURAL, record)

        state_b = await mem_b.perceive(_make_state())
        b_contents = [r.content for r in state_b.retrieved_context]
        self.assertIn("shared-skill: use_tool", b_contents)

    async def test_both_semantic_and_procedural_shared(self) -> None:
        store = TeamSharedMemoryStore([MemoryLayer.SEMANTIC, MemoryLayer.PROCEDURAL])
        mem_a = SimpleMemorySystem()
        mem_b = SimpleMemorySystem()
        mem_a = SimpleMemorySystem(shared_store=store)  # was bind
        mem_b = SimpleMemorySystem(shared_store=store)  # was bind

        mem_a.write_shared_record(MemoryLayer.SEMANTIC, _make_semantic_record("fact-1"))
        mem_a.write_shared_record(
            MemoryLayer.PROCEDURAL,
            MemoryRecord(
                record_id="proc-1",
                content="skill-1",
                memory_type=MemoryLayer.PROCEDURAL,
                importance=0.7,
            ),
        )

        state_b = await mem_b.perceive(_make_state())
        b_contents = [r.content for r in state_b.retrieved_context]
        self.assertIn("fact-1", b_contents)
        self.assertIn("skill-1", b_contents)


class TestEpisodicWorkingRemainPrivate(unittest.IsolatedAsyncioTestCase):
    """即使在共享模式下，episodic/working 层也保持私有（CoALA 语义边界）。"""

    async def test_episodic_remains_private_with_shared_semantic(self) -> None:
        store = TeamSharedMemoryStore([MemoryLayer.SEMANTIC])
        mem_a = SimpleMemorySystem()
        mem_b = SimpleMemorySystem()
        mem_a = SimpleMemorySystem(shared_store=store)  # was bind
        mem_b = SimpleMemorySystem(shared_store=store)  # was bind

        # 通过 update 触发 episodic 写入
        await mem_a.update(_make_state("trace-a"), _make_observation(), _make_reflection())

        state_a = await mem_a.perceive(_make_state("trace-a"))
        state_b = await mem_b.perceive(_make_state("trace-b"))

        a_episodic = [r for r in state_a.retrieved_context if r.memory_type == MemoryLayer.EPISODIC]
        b_episodic = [r for r in state_b.retrieved_context if r.memory_type == MemoryLayer.EPISODIC]

        self.assertEqual(len(a_episodic), 1)
        self.assertEqual(len(b_episodic), 0)

    async def test_working_remains_private_with_shared_semantic(self) -> None:
        store = TeamSharedMemoryStore([MemoryLayer.SEMANTIC])
        mem_a = SimpleMemorySystem()
        mem_b = SimpleMemorySystem()
        mem_a = SimpleMemorySystem(shared_store=store)  # was bind
        mem_b = SimpleMemorySystem(shared_store=store)  # was bind

        await mem_a.update(
            _make_state("trace-a"),
            _make_observation(success=True, payload="result-data"),
            _make_reflection(),
        )

        state_b = await mem_b.perceive(_make_state("trace-b"))
        b_working = [r for r in state_b.retrieved_context if r.memory_type == MemoryLayer.WORKING]
        self.assertEqual(len(b_working), 0)


class TestWriteSharedRecordGuard(unittest.TestCase):
    """write_shared_record 的防御性检查。"""

    def test_write_to_unshared_layer_raises(self) -> None:
        mem = SimpleMemorySystem()
        store = TeamSharedMemoryStore([MemoryLayer.SEMANTIC])
        mem = SimpleMemorySystem(shared_store=store)  # was bind

        with self.assertRaises(KeyError):
            mem.write_shared_record(MemoryLayer.EPISODIC, _make_semantic_record("x"))

    def test_write_without_store_raises(self) -> None:
        mem = SimpleMemorySystem()
        with self.assertRaises(KeyError):
            mem.write_shared_record(MemoryLayer.SEMANTIC, _make_semantic_record("x"))


class TestTeamOrchestratorSharedMemoryInjection(unittest.IsolatedAsyncioTestCase):
    """Assembly.assemble_team rebuilds members with shared store (closed graph)."""

    async def test_orchestrator_injects_shared_memory(self) -> None:
        from lca.contracts.team_coordination import (
            Pipeline,
        )
        from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
        from lca.layer4_app.composer import TeamComposer
        from tests.support.agent_specs import make_spec

        asm = TeamComposer()
        llm = MockLLMAdapter()
        team = asm.compose_team(
            members=[make_spec("agent_a", llm), make_spec("agent_b", llm)],
            coordination=Pipeline(),
            shared_memory_layers=[MemoryLayer.SEMANTIC],
        )
        self.assertIsNotNone(team._context.shared_memory)
        mem_a = team.members[0].runtime.memory  # type: ignore[attr-defined]
        mem_b = team.members[1].runtime.memory  # type: ignore[attr-defined]
        mem_a.write_shared_record(
            MemoryLayer.SEMANTIC, _make_semantic_record("orchestrator-shared-fact")
        )
        state_b = await mem_b.perceive(_make_state())
        b_contents = [r.content for r in state_b.retrieved_context]
        self.assertIn("orchestrator-shared-fact", b_contents)

    async def test_orchestrator_no_shared_memory_when_config_empty(self) -> None:
        from lca.contracts.team_coordination import (
            Pipeline,
        )
        from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
        from lca.layer4_app.composer import TeamComposer
        from tests.support.agent_specs import make_spec

        asm = TeamComposer()
        llm = MockLLMAdapter()
        team = asm.compose_team(
            members=[make_spec("agent_a", llm), make_spec("agent_b", llm)],
            coordination=Pipeline(),
            shared_memory_layers=[],
        )
        self.assertIsNone(team._context.shared_memory)
        mem_a = team.members[0].runtime.memory  # type: ignore[attr-defined]
        mem_b = team.members[1].runtime.memory  # type: ignore[attr-defined]
        mem_a._private_layers[MemoryLayer.SEMANTIC].append(_make_semantic_record("private-to-a"))
        state_b = await mem_b.perceive(_make_state())
        b_contents = [r.content for r in state_b.retrieved_context]
        self.assertNotIn("private-to-a", b_contents)


def _make_minimal_runtime(memory: SimpleMemorySystem):
    """构建最小化 Runtime 桩件，仅支持 run()。"""
    from unittest.mock import AsyncMock, MagicMock

    from lca.contracts.result import Result
    from lca.contracts.state import Budget

    runtime = MagicMock()
    runtime.body = MagicMock()
    runtime.brain = MagicMock()
    runtime.memory = memory
    runtime.run = AsyncMock(
        return_value=Result(
            trace_id="mock",
            status="completed",
            output="ok",
            final_state_ref="",
            total_steps=1,
            budget_used=Budget(),
        )
    )
    return runtime


if __name__ == "__main__":
    unittest.main()
