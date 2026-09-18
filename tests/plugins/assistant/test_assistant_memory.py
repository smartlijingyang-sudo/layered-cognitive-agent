"""AssistantMemory tests (ADR-0242 D5 / I-B5).

Covers:
- ``update`` persists records under ``{home}/memory/``;
- two instances over the same home share records (跨 run 持久);
- two different homes are isolated (跨 assistant 不可见);
- ``build_solo_agent`` accepts a ``MemorySystem`` and passes it to Agent.
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.atoms.enums.enums import MemoryLayer, ReflectionVerdict
from lca.contracts.models.core.execution.decision import Observation, Reflection
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.plugins.collaboration.modes.solo import build_solo_agent
from tests.harness.collector import InMemoryObservability
from tests.harness.scripted_llm import ScriptedLLMAdapter


class _StubState:
    def __init__(self, step: int = 1, trace_id: str = "trace_x") -> None:
        self.step = step
        self.trace_id = trace_id


def _observation() -> Observation:
    return Observation(
        observation_id="obs_x",
        success=True,
        payload={"answer": 42},
        latency_ms=1,
    )


def _reflection() -> Reflection:
    return Reflection(
        reflection_id="ref_x",
        verdict=ReflectionVerdict.ON_TRACK,
        lesson="done",
    )


class TestAssistantMemory:
    def test_update_persists_to_home_memory_dir(self, tmp_path: Path) -> None:
        home = tmp_path / "asst_home"
        home.mkdir()
        mem = AssistantMemory(home)
        import asyncio

        asyncio.run(mem.update(_StubState(), _observation(), _reflection()))
        records = mem.query(MemoryLayer.WORKING)
        assert len(records) == 1
        assert records[0].content.startswith("step=1")
        assert (home / "memory").is_dir()

    def test_two_instances_share_persisted_records(self, tmp_path: Path) -> None:
        """同一 assistant Home 上两个实例（两次 run）共享记忆（I-B5 跨 run 持久）。"""
        home = tmp_path / "asst_home"
        home.mkdir()
        import asyncio

        asyncio.run(AssistantMemory(home).update(_StubState(step=1), _observation(), _reflection()))
        second = AssistantMemory(home)
        records = second.query(MemoryLayer.WORKING)
        assert len(records) == 1
        assert records[0].content.startswith("step=1")

    def test_two_homes_are_isolated(self, tmp_path: Path) -> None:
        """两个 assistant Home 的 memory 互不可见（I-B5 跨 assistant 隔离）。"""
        import asyncio

        home_a = tmp_path / "asst_a"
        home_b = tmp_path / "asst_b"
        home_a.mkdir()
        home_b.mkdir()
        asyncio.run(AssistantMemory(home_a).update(_StubState(), _observation(), _reflection()))
        assert AssistantMemory(home_b).query(MemoryLayer.WORKING) == []

    def test_query_unknown_layer_returns_empty(self, tmp_path: Path) -> None:
        home = tmp_path / "asst_home"
        home.mkdir()
        assert AssistantMemory(home).query(MemoryLayer.PROCEDURAL) == []


class TestSoloAgentMemoryWiring:
    def test_build_solo_agent_passes_memory(self, tmp_path: Path) -> None:
        llm = ScriptedLLMAdapter({}, default_respond=True)
        home = tmp_path / "asst_home"
        mem = AssistantMemory(home)
        agent = build_solo_agent(
            llm,
            observability=InMemoryObservability(),
            memory=mem,
        )
        assert agent._spec.memory is mem

    def test_build_solo_agent_without_memory_uses_default(self) -> None:
        llm = ScriptedLLMAdapter({}, default_respond=True)
        agent = build_solo_agent(llm, observability=InMemoryObservability())
        from lca.contracts.protocols.journal.spec.spec import MEMORY_CHOICE_SIMPLE

        assert agent._spec.memory == MEMORY_CHOICE_SIMPLE
