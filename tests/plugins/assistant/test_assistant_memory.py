"""AssistantMemory tests (ADR-0242 D5 / I-B5).

Covers:
- ``update`` persists records under ``{home}/memory/``;
- two instances over the same home share records (跨 run 持久);
- two different homes are isolated (跨 assistant 不可见);
- ``build_solo_agent`` accepts a ``MemorySystem`` and passes it to Agent.
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer, ReflectionVerdict
from lca.contracts.models.core.conversation.memory import MemoryRecord
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


class TestMemoryDedupeAndBackfill:
    """ADR-0247 回归：canonical dedupe_key、内容指纹去重、写路径回填。"""

    @staticmethod
    def _pref(
        record_id: str,
        content: str,
        dedupe_key: str | None = None,
    ) -> MemoryRecord:
        return MemoryRecord(
            record_id=record_id,
            content=content,
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.9,
            category=MemoryCategory.PREFERENCE,
            dedupe_key=dedupe_key,
            confidence=1.0,
        )

    def test_canonical_dedupe_key_normalization(self, tmp_path: Path) -> None:
        """同 category 下不带前缀与带前缀/连字符的 dedupe_key 规范化为统一键并收敛。"""
        home = tmp_path / "asst_home"
        home.mkdir()
        mem = AssistantMemory(home)
        mem.upsert(self._pref("mem_a", "用户偏好：风格简洁", dedupe_key="style"))
        mem.upsert(
            self._pref(
                "mem_b",
                "用户偏好：风格简洁",
                dedupe_key="preference:style",
            )
        )
        records = mem.query(MemoryLayer.SEMANTIC)
        assert len(records) == 1
        assert records[0].dedupe_key == "preference:style"

    def test_content_fingerprint_collapses_phrasing(self, tmp_path: Path) -> None:
        """不同标签前缀与引号变体表达同一偏好时，内容指纹收敛为一条活跃记录。"""
        home = tmp_path / "asst_home"
        home.mkdir()
        mem = AssistantMemory(home)
        mem.upsert(self._pref("mem_a", "用户偏好：不喜欢啰嗦"))
        mem.upsert(self._pref("mem_b", "偏好：不喜欢啰嗦"))
        mem.upsert(self._pref("mem_c", '用户偏好：不喜欢"啰嗦"'))
        records = mem.query(MemoryLayer.SEMANTIC)
        assert len(records) == 1
        # 写路径内容级去重保留最新写入的一条。
        assert records[0].content == '用户偏好：不喜欢"啰嗦"'

    def test_upsert_triggers_profile_backfill(self, tmp_path: Path) -> None:
        """memory_add 路径（upsert）写入身份/偏好后触发 USER.md 回填。"""
        from lca.infrastructure.tools.assistant.memory_tools import MemoryAddTool

        home = tmp_path / "asst_home"
        home.mkdir()
        calls: list[tuple[str, list[str]]] = []

        async def backfill(assistant_id: str, records: list[MemoryRecord]) -> None:
            calls.append((assistant_id, [r.content for r in records]))

        mem = AssistantMemory(home, profile_backfill=backfill)
        import asyncio

        asyncio.run(
            MemoryAddTool(memory=mem).execute(
                {"content": "用户身份：架构师", "category": "identity"}
            )
        )
        assert len(calls) == 1
        assert calls[0][0] == "asst_home"
        assert "用户身份：架构师" in calls[0][1]

    def test_supersede_triggers_profile_backfill(self, tmp_path: Path) -> None:
        """memory_update 路径（supersede）替换身份/偏好后触发 USER.md 回填。"""
        from lca.infrastructure.tools.assistant.memory_tools import MemoryUpdateTool

        home = tmp_path / "asst_home"
        home.mkdir()
        calls: list[tuple[str, list[str]]] = []

        async def backfill(assistant_id: str, records: list[MemoryRecord]) -> None:
            calls.append((assistant_id, [r.content for r in records]))

        mem = AssistantMemory(home, profile_backfill=backfill)
        mem.upsert(self._pref("mem_old", "用户偏好：Rust", dedupe_key="preference:tech_stack"))
        calls.clear()
        import asyncio

        asyncio.run(
            MemoryUpdateTool(memory=mem).execute(
                {
                    "record_id": "mem_old",
                    "content": "用户偏好：Python",
                    "category": "preference",
                    "dedupe_key": "preference:tech_stack",
                }
            )
        )
        assert len(calls) == 1
        assert calls[0][0] == "asst_home"
        assert "用户偏好：Python" in calls[0][1]
        assert "用户偏好：Rust" not in calls[0][1]

    def test_remove_triggers_profile_backfill(self, tmp_path: Path) -> None:
        """memory_remove 路径（remove）删除身份/偏好后触发 USER.md 回填。"""
        from lca.infrastructure.tools.assistant.memory_tools import MemoryRemoveTool

        home = tmp_path / "asst_home"
        home.mkdir()
        calls: list[tuple[str, list[str]]] = []

        async def backfill(assistant_id: str, records: list[MemoryRecord]) -> None:
            calls.append((assistant_id, [r.content for r in records]))

        mem = AssistantMemory(home, profile_backfill=backfill)
        mem.upsert(self._pref("mem_a", "用户偏好：Python", dedupe_key="preference:tech_stack"))
        calls.clear()
        import asyncio

        asyncio.run(MemoryRemoveTool(memory=mem).execute({"record_id": "mem_a", "confirmed": True}))
        assert len(calls) == 1
        assert calls[0][0] == "asst_home"
        assert calls[0][1] == []
