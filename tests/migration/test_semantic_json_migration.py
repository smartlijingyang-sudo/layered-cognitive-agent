"""PR-9（ADR-0246）：旧 semantic.json 原文记录迁移为 superseded。"""

from __future__ import annotations

import json

from lca.contracts.atoms.enums.enums import MemoryLayer
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.migration import (
    clean_lowercase_user_md,
    migrate_semantic_memory,
)


def _write_old_semantic(home, tmp_path) -> None:
    memory_dir = tmp_path / home / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "semantic.json").write_text(
        json.dumps(
            [
                {
                    "record_id": "mem_old_1",
                    "layer": "semantic",
                    "content": "用户原文整句：记住我，我是架构师",
                    "importance": 0.5,
                    "source_trace_id": "trace_1",
                    "created_at": "2026-09-20T00:00:00Z",
                    "metadata": {"source": "user"},
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_migrate_marks_old_records_superseded(tmp_path) -> None:
    _write_old_semantic("asst", tmp_path)
    home = tmp_path / "asst"

    changed = migrate_semantic_memory(home)
    assert changed == 1

    records = json.loads((home / "memory" / "semantic.json").read_text(encoding="utf-8"))
    assert records[0]["deleted"] is True
    assert records[0]["retired_at_ms"] is not None
    assert records[0]["metadata"]["migrated"] == "superseded_raw_text"


def test_migrated_records_excluded_from_retrieval(tmp_path) -> None:
    _write_old_semantic("asst", tmp_path)
    home = tmp_path / "asst"
    migrate_semantic_memory(home)

    memory = AssistantMemory(home)
    active = memory.query(MemoryLayer.SEMANTIC)
    assert active == []


def test_migrate_missing_file_is_noop(tmp_path) -> None:
    assert migrate_semantic_memory(tmp_path / "asst") == 0


def test_clean_lowercase_user_md_backfills(tmp_path) -> None:
    home = tmp_path / "asst"
    home.mkdir(parents=True, exist_ok=True)
    (home / "user.md").write_text("我是架构师\n", encoding="utf-8")
    (home / "USER.md").write_text("", encoding="utf-8")

    assert clean_lowercase_user_md(home) is True
    assert not (home / "user.md").exists()
    assert "架构师" in (home / "USER.md").read_text(encoding="utf-8")


def test_dedupe_semantic_memory_keeps_highest_authority(tmp_path) -> None:
    """同一 canonical key 的重复活跃记录去重，保留 source=user 权威最高一条。"""
    from lca.infrastructure.memory.migration import dedupe_semantic_memory

    home = tmp_path / "asst"
    memory_dir = home / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "semantic.json").write_text(
        json.dumps(
            [
                {
                    "record_id": "mem_user",
                    "layer": "semantic",
                    "category": "preference",
                    "content": "技术栈偏好：Python（弃用 Rust 与 Go）",
                    "importance": 0.9,
                    "confidence": 1.0,
                    "source": "user",
                    "dedupe_key": "tech_stack",
                    "deleted": False,
                    "created_at_ms": 100,
                    "metadata": {"source": "user"},
                },
                {
                    "record_id": "mem_model",
                    "layer": "semantic",
                    "category": "preference",
                    "content": "用户技术栈偏好：Python（弃用 Rust 和 Go）",
                    "importance": 0.9,
                    "confidence": 0.9,
                    "source": "model",
                    "dedupe_key": "preference:tech_stack",
                    "deleted": False,
                    "created_at_ms": 200,
                    "metadata": {"source": "model"},
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    changed = dedupe_semantic_memory(home)
    assert changed == 1

    records = json.loads((memory_dir / "semantic.json").read_text(encoding="utf-8"))
    by_id = {r["record_id"]: r for r in records}
    assert by_id["mem_user"]["deleted"] is False
    assert by_id["mem_user"]["dedupe_key"] == "preference:tech_stack"
    assert by_id["mem_model"]["deleted"] is True
    assert by_id["mem_model"]["metadata"]["superseded_reason"] == "deduped"


def test_dedupe_canonicalizes_singleton_keys(tmp_path) -> None:
    """无重复的活跃记录也把 dedupe_key 改写为 canonical key 并落盘。"""
    from lca.infrastructure.memory.migration import dedupe_semantic_memory

    home = tmp_path / "asst"
    memory_dir = home / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "semantic.json").write_text(
        json.dumps(
            [
                {
                    "record_id": "mem_solo",
                    "layer": "semantic",
                    "category": "preference",
                    "content": "用户偏好：严禁引入重量级依赖",
                    "importance": 0.9,
                    "confidence": 1.0,
                    "source": "user",
                    "dedupe_key": "preference:dependency-control",
                    "deleted": False,
                    "created_at_ms": 100,
                    "metadata": {"source": "user"},
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    changed = dedupe_semantic_memory(home)
    assert changed == 0

    records = json.loads((memory_dir / "semantic.json").read_text(encoding="utf-8"))
    assert records[0]["dedupe_key"] == "preference:dependency_control"
