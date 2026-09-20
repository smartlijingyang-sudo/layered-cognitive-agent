"""PR-1（ADR-0246）：``MemoryStore`` / ``MemoryTool`` 协议契约测试。"""

from __future__ import annotations

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.protocols.memory.memory import MemoryStore, MemoryTool


class TestMemoryStoreProtocol:
    def test_protocol_is_runtime_checkable(self) -> None:
        """``runtime_checkable`` 使结构化匹配可通过 ``isinstance`` 判定。"""

        class FakeStore:
            def upsert(self, record):
                return record

            def supersede(self, record_id, replacement, *, reason="superseded"):
                return replacement

            def query(self, *, category=None, include_superseded=False, limit=50):
                return []

        assert isinstance(FakeStore(), MemoryStore)

    def test_protocol_has_required_methods(self) -> None:
        assert hasattr(MemoryStore, "upsert")
        assert hasattr(MemoryStore, "supersede")
        assert hasattr(MemoryStore, "query")

    def test_runtime_check_accepts_structural_match(self) -> None:
        class FakeStore:
            def upsert(self, record):
                return record

            def supersede(self, record_id, replacement, *, reason="superseded"):
                return replacement

            def query(self, *, category=None, include_superseded=False, limit=50):
                return []

        assert isinstance(FakeStore(), MemoryStore)

    def test_runtime_check_rejects_missing_method(self) -> None:
        class Empty:
            pass

        assert not isinstance(Empty(), MemoryStore)


class TestMemoryToolProtocol:
    def test_protocol_is_runtime_checkable(self) -> None:
        """``runtime_checkable`` 使结构化匹配可通过 ``isinstance`` 判定。"""

        class FakeTool:
            name = "memory_search"
            description = "search memory"

            def search(self, query, *, limit=5):
                return []

            def add(self, record):
                return record

            def update(self, record_id, record):
                return record

            def remove(self, record_id):
                return None

        assert isinstance(FakeTool(), MemoryTool)

    def test_protocol_has_required_operations(self) -> None:
        assert hasattr(MemoryTool, "search")
        assert hasattr(MemoryTool, "add")
        assert hasattr(MemoryTool, "update")
        assert hasattr(MemoryTool, "remove")

    def test_runtime_check_accepts_structural_match(self) -> None:
        class FakeTool:
            name = "memory_search"
            description = "search memory"

            def search(self, query, *, limit=5):
                return []

            def add(self, record):
                return record

            def update(self, record_id, record):
                return record

            def remove(self, record_id):
                return None

        assert isinstance(FakeTool(), MemoryTool)

    def test_runtime_check_rejects_missing_operation(self) -> None:
        class PartialTool:
            name = "memory_add"
            description = "add memory"

            def add(self, record):
                return record

        assert not isinstance(PartialTool(), MemoryTool)


def test_memory_record_roundtrip_via_protocol_shape() -> None:
    """结构化记忆记录可被 ``MemoryStore`` 形状的对象读写。"""
    record = MemoryRecord(
        record_id="mem_p1",
        content="用户偏好：不喜欢啰嗦",
        memory_type=MemoryLayer.SEMANTIC,
        importance=0.8,
        category=MemoryCategory.PREFERENCE,
        dedupe_key="preference:concise",
    )

    class FakeStore:
        def __init__(self):
            self._records = [record]

        def upsert(self, record):
            self._records = [r for r in self._records if r.record_id != record.record_id]
            self._records.append(record)
            return record

        def supersede(self, record_id, replacement, *, reason="superseded"):
            return replacement

        def query(self, *, category=None, include_superseded=False, limit=50):
            return [r for r in self._records if r.category == category][:limit]

    assert isinstance(FakeStore(), MemoryStore)
    assert (
        FakeStore().query(category=MemoryCategory.PREFERENCE)[0].content == "用户偏好：不喜欢啰嗦"
    )
