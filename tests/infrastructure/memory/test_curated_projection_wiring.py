"""Wiring tests: _project_curated -> plan_curated_memory_projection.

Design-doc requirement (stateless memory projection): the disk-cache refresh
must go through the single record->claim mapping in curated.py
(``curated_claims_from_records``), not a divergent local mapper.

The secret-filtering assertion is the wiring proof: the old local mapper
(``_claims_from_records``) had no secret filter, so a secret reaching disk
would mean the old path is still live. Records are written via ``_save``
directly to bypass the write-time credential gate in ``_append_semantic`` and
exercise the projection-layer filter specifically.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.contextfiles.domain.curated import (
    curated_claims_from_records,
    may_acknowledge_projection,
    plan_curated_memory_projection,
    render_curated_memory_markdown,
)


def _entry(content: str, category: str, **kw) -> dict:
    entry = {
        "record_id": new_id("mem"),
        "content": content,
        "category": category,
        "layer": MemoryLayer.SEMANTIC.value,
        "importance": 0.9,
        "dedupe_key": new_id("key"),
        "confidence": 0.9,
        "metadata": {"source": "tool:memory_add"},
    }
    entry.update(kw)
    return entry


def test_project_curated_refreshes_disk_through_single_mapping(tmp_path: Path) -> None:
    home = tmp_path / "asst_wire"
    home.mkdir(parents=True, exist_ok=True)
    memory = AssistantMemory(home)

    records = [
        _entry("用户的开发语言是 Rust", "fact"),
        _entry("用户习惯暗黑模式", "preference"),
        _entry("用户真名叫张三", "identity"),
        _entry("这条记录已删除", "fact", deleted=True),
        _entry("deploy api_key=sk-test1234567890abcdef", "fact"),
    ]
    memory._save(MemoryLayer.SEMANTIC, records, committed_ids=("mem_e2e_1",))

    md_path = home / "MEMORY.md"
    assert md_path.is_file(), "projection must refresh the disk cache"
    text = md_path.read_text(encoding="utf-8")

    assert "用户的开发语言是 Rust" in text
    assert "用户习惯暗黑模式" in text
    assert "用户真名叫张三" not in text, "identity must not leak into MEMORY.md"
    assert "这条记录已删除" not in text
    assert "sk-test1234567890abcdef" not in text, (
        "secret-bearing record reached disk: the old unfiltered mapper is still live"
    )

    receipt = memory.last_curated_receipt
    assert receipt is not None and receipt.ok
    assert receipt.byte_count > 0
    assert receipt.record_ids == ("mem_e2e_1",)
    assert may_acknowledge_projection(receipt)


def test_single_mapping_filters_deleted_identity_and_secrets() -> None:
    records = [
        SimpleNamespace(
            record_id="mem_1", deleted=False, category=MemoryCategory.FACT,
            content="事实一", importance=0.9, metadata={},
            source="", created_at_ms=None,
        ),
        SimpleNamespace(
            record_id="mem_2", deleted=True, category=MemoryCategory.FACT,
            content="删掉一", importance=0.9, metadata={},
            source="", created_at_ms=None,
        ),
        SimpleNamespace(
            record_id="mem_3", deleted=False, category=MemoryCategory.IDENTITY,
            content="身份一", importance=0.9, metadata={},
            source="", created_at_ms=None,
        ),
        SimpleNamespace(
            record_id="mem_4", deleted=False, category=MemoryCategory.FACT,
            content="token=sk-live-abcdef1234567890", importance=0.9,
            metadata={}, source="", created_at_ms=None,
        ),
    ]
    claims = curated_claims_from_records(records)
    assert [c.claim_id for c in claims] == ["mem_1"]
    text = render_curated_memory_markdown(records)
    assert "事实一" in text
    assert "删掉一" not in text and "身份一" not in text
    assert "sk-live-abcdef1234567890" not in text


def test_render_and_plan_share_single_mapping_path() -> None:
    records = [
        MemoryRecord(
            record_id=new_id("mem"), content="事实一",
            category=MemoryCategory.FACT, memory_type=MemoryLayer.SEMANTIC,
            importance=0.9, dedupe_key=new_id("key"), confidence=0.9,
            metadata={"source": "tool:memory_add"},
        ),
        MemoryRecord(
            record_id=new_id("mem"), content="偏好一",
            category=MemoryCategory.PREFERENCE, memory_type=MemoryLayer.SEMANTIC,
            importance=0.9, dedupe_key=new_id("key"), confidence=0.9,
            metadata={"source": "tool:memory_add"},
        ),
    ]
    text, omitted = plan_curated_memory_projection(records, source_note="n")
    assert render_curated_memory_markdown(records, source_note="n") == text
    assert isinstance(omitted, tuple)
    assert "事实一" in text and "偏好一" in text


def test_plan_reports_budget_omitted_claims() -> None:
    records = [
        MemoryRecord(
            record_id=new_id("mem"), content=f"事实内容{i:03d} 补充补充补充补充补充",
            category=MemoryCategory.FACT, memory_type=MemoryLayer.SEMANTIC,
            importance=0.9, dedupe_key=new_id("key"), confidence=0.9,
            metadata={"source": "tool:memory_add"},
        )
        for i in range(30)
    ]
    full_text, full_omitted = plan_curated_memory_projection(records)
    tiny_text, tiny_omitted = plan_curated_memory_projection(records, char_budget=400)
    assert not full_omitted, "default budget fits 30 short claims"
    assert tiny_omitted, "tiny budget must omit claims instead of silently dropping them"
    assert len(tiny_text) < len(full_text)
    assert {c.body for c in tiny_omitted}, "omitted claims carry bodies for the archive input"
