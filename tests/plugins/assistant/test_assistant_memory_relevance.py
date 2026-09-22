"""Tests for AssistantMemory relevance-driven retrieval and token budget pruning."""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.infrastructure.memory.assistant_memory import AssistantMemory


@pytest.mark.asyncio
async def test_assistant_memory_retrieves_relevant_records_first(tmp_path: Path):
    mem = AssistantMemory(tmp_path / "asst")
    mem.upsert(
        MemoryRecord(
            record_id="m1",
            content="项目核心技术栈为 Python 3.12 与 FastAPI 框架",
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.8,
            category=MemoryCategory.FACT,
            created_at_ms=1000,
        )
    )
    mem.upsert(
        MemoryRecord(
            record_id="m2",
            content="Redis 生产缓存集群端口为 6379，主从高可用",
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.8,
            category=MemoryCategory.FACT,
            created_at_ms=2000,
        )
    )
    mem.upsert(
        MemoryRecord(
            record_id="m3",
            content="Kubernetes 部署命名空间为 production-lca",
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.8,
            category=MemoryCategory.FACT,
            created_at_ms=3000,
        )
    )

    # 检索关于 Redis 的问题，即便它在文件中排第二，在检索结果中也必须排在第一位
    results = await mem.retrieve(None, query="Redis 缓存配置与端口", token_budget=1000)
    assert len(results) >= 1
    assert "Redis" in results[0].content


@pytest.mark.asyncio
async def test_assistant_memory_prunes_irrelevant_records_on_tight_budget(tmp_path: Path):
    mem = AssistantMemory(tmp_path / "asst")
    mem.upsert(
        MemoryRecord(
            record_id="m_irrelevant",
            content="这是一个与主题完全无关的冗长历史陈述，包含大量无关的无用字符与段落文字",
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.5,
            category=MemoryCategory.FACT,
            created_at_ms=1000,
        )
    )
    mem.upsert(
        MemoryRecord(
            record_id="m_relevant",
            content="PostgreSQL 连接池大小限制为 20",
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.9,
            category=MemoryCategory.FACT,
            created_at_ms=2000,
        )
    )

    # 紧凑预算（例如 15 tokens），最相关的 PostgreSQL 必须被保留，排在第一位
    results = await mem.retrieve(None, query="PostgreSQL 数据库配置", token_budget=20)
    assert len(results) >= 1
    assert "PostgreSQL" in results[0].content
