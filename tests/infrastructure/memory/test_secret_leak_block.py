"""INV-SECRET-SANITIZATION-FAIL-LOUD — credential-shaped content never lands."""

from __future__ import annotations

from types import SimpleNamespace

from lca.cognition.memory.acknowledgement import guard_reply
from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.domain.curated import contains_secret


def test_contains_secret_detects_credential_shapes() -> None:
    assert contains_secret("api_key=sk-1234567890abcdef")
    assert contains_secret("password: hunter2")
    assert contains_secret("API Key = abcdef123456")
    assert contains_secret("export AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")
    assert contains_secret("c2stcHJvai1hYmNkZWZnaGlqa2xtbm9wcXJzdHV2d3h5ejEyMzQ1Njc4OTA=")
    assert contains_secret("数据库密码就是 admin888")
    assert contains_secret(
        __import__("base64")
        .urlsafe_b64encode(b"sk-proj-abcdefghijklmnopqrstuvwxyz1234567890")
        .decode()
    )
    assert not contains_secret("用户住在杭州")
    assert not contains_secret("密码就是记不住")


def test_memory_add_rejects_credential_content(tmp_path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    memory.upsert(
        MemoryRecord(
            record_id="leak-1",
            content="密码: hunter2",
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.9,
            category=MemoryCategory.FACT,
            dedupe_key="leak",
            confidence=1.0,
            metadata={"source": "user"},
        )
    )
    assert memory.query(MemoryLayer.SEMANTIC) == []
    assert memory.last_curated_receipt is not None
    assert memory.last_curated_receipt.ok is False
    assert memory.last_curated_receipt.error == "credential_rejected"


def test_projection_never_contains_credentials(tmp_path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    memory.upsert(
        MemoryRecord(
            record_id="ok-1",
            content="用户住在杭州",
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.9,
            category=MemoryCategory.FACT,
            dedupe_key="city",
            confidence=1.0,
            metadata={"source": "user"},
        )
    )
    memory.upsert(
        MemoryRecord(
            record_id="leak-2",
            content="token: sk-1234567890abcdef",
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.9,
            category=MemoryCategory.FACT,
            dedupe_key="token",
            confidence=1.0,
            metadata={"source": "user"},
        )
    )
    projected = (tmp_path / "asst" / "MEMORY.md").read_text(encoding="utf-8")
    assert "用户住在杭州" in projected
    assert "sk-1234567890abcdef" not in projected
    assert "密码" not in projected


def test_projection_failure_rolls_back_semantic_json(tmp_path, monkeypatch) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    memory.upsert(
        MemoryRecord(
            record_id="ok-1",
            content="用户住在杭州",
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.9,
            category=MemoryCategory.FACT,
            dedupe_key="city",
            confidence=1.0,
            metadata={"source": "user"},
        )
    )
    original = (tmp_path / "asst" / "memory" / "semantic.json").read_text(encoding="utf-8")

    def _boom(self, relative_path: str, text: str) -> None:
        del self, relative_path, text
        raise OSError("read-only")

    monkeypatch.setattr(DiskFileStore, "atomic_replace", _boom)
    memory.upsert(
        MemoryRecord(
            record_id="ok-2",
            content="用户搬到北京",
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.9,
            category=MemoryCategory.FACT,
            dedupe_key="city-2",
            confidence=1.0,
            metadata={"source": "user"},
        )
    )
    assert memory.last_curated_receipt is not None
    assert memory.last_curated_receipt.ok is False
    assert (tmp_path / "asst" / "memory" / "semantic.json").read_text(encoding="utf-8") == original
    assert all(record.content != "用户搬到北京" for record in memory.query(MemoryLayer.SEMANTIC))


def test_claim_latch_survives_a_new_process_handle(tmp_path) -> None:
    first = AssistantMemory(tmp_path / "asst")
    first.upsert(
        MemoryRecord(
            record_id="ok-1",
            content="用户住在杭州",
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.9,
            category=MemoryCategory.FACT,
            dedupe_key="city",
            confidence=1.0,
            metadata={"source": "user"},
        )
    )
    runtime = SimpleNamespace(memory=AssistantMemory(tmp_path / "asst"))
    assert guard_reply("我记下了。", runtime) == "我记下了。"
    assert guard_reply("已经记录了。", runtime) == "这条还没有写入记忆文件。我不能说已经记下。"


def test_misdiagnosis_stays_when_the_projection_is_over_budget() -> None:
    from lca.infrastructure.memory.contextfiles.domain.curated import (
        CuratedClaim,
        plan_curated_projection,
    )

    lesson = CuratedClaim(
        claim_id="lesson-1",
        kind="fact",
        body="此前误诊：单向依赖被画成双向",
        importance=0.1,
    )
    filler = CuratedClaim(
        claim_id="pad-1",
        kind="fact",
        body="填充条目 " + ("很长" * 40),
        importance=0.9,
    )
    text, omitted = plan_curated_projection((lesson, filler), char_budget=180)
    assert "此前误诊" in text
    assert omitted
    assert omitted[0].claim_id == "pad-1"


def test_overflow_claims_are_archived_on_disk(tmp_path) -> None:
    from lca.infrastructure.memory.contextfiles.domain.curated import CuratedClaim

    memory = AssistantMemory(tmp_path / "asst")
    memory._archive_omitted(
        (
            CuratedClaim(
                claim_id="pad-1",
                kind="fact",
                body="被预算挤出的条目",
                importance=0.2,
            ),
        )
    )
    archives = list((tmp_path / "asst" / "revisions").glob("archive_*.md"))
    assert archives
    assert "pad-1" in archives[0].read_text(encoding="utf-8")
    assert "被预算挤出的条目" in archives[0].read_text(encoding="utf-8")
