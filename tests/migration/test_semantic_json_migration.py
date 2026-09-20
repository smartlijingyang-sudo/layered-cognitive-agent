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
