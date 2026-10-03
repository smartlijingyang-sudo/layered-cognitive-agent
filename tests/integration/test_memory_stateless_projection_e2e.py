"""End-to-end integration tests for stateless memory projection and writeback.

Verifies:
- INV-MEM-01: semantic.json as single source of truth (SSOT).
- INV-MEM-02: MEMORY.md as deterministic pure functional projection.
- INV-MEM-03: Persistent skeleton: ## Preferences and ## Facts headers are preserved even when empty.
- INV-MEM-04: Markdown edit sync reconciles ADD, SUPERSEDE, and DELETE back to semantic.json.
- INV-MEM-05: Roundtrip idempotency between projection and edit parser.
- INV-MEM-06: Prompt context assembly (persona_from_home / refresh_standing_backstory)
  instantaneously reflects memory evolution across all states.
"""

from __future__ import annotations

import json
from pathlib import Path

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.contextfiles.service.assembly import refresh_standing_backstory
from lca.infrastructure.memory.contextfiles.service.memory_edit_sync import MemoryEditSyncService
from lca.plugins.assistant.persona.persona import persona_from_home


def test_memory_stateless_projection_and_writeback_lifecycle(tmp_path: Path) -> None:
    home = tmp_path / "asst_lifecycle_test"
    home.mkdir(parents=True, exist_ok=True)
    memory_path = home / "MEMORY.md"
    semantic_json_path = home / "memory" / "semantic.json"

    # Step 1: Initial state — initialize AssistantMemory
    memory = AssistantMemory(home)
    assert not memory_path.is_file(), "MEMORY.md does not exist until first projection"
    assert not semantic_json_path.is_file(), "semantic.json does not exist until first write"

    # Trigger initial projection (e.g. empty or default)
    memory._project_curated(())
    assert memory_path.is_file()
    initial_md = memory_path.read_text(encoding="utf-8")
    assert "## Preferences" in initial_md
    assert "## Facts" in initial_md
    assert "暂无" in initial_md, "Skeleton placeholders preserved even with zero records"

    # Check persona_from_home prompt assembly
    persona_0 = persona_from_home(str(home))
    assert "<!-- INJECTED FILE: MEMORY.md -->" in persona_0.backstory
    assert "## Preferences" in persona_0.backstory
    assert "## Facts" in persona_0.backstory

    # Step 2: Autonomous Tool / Cognitive write: Add preference & fact via AssistantMemory
    pref_rec = MemoryRecord(
        record_id=new_id("mem"),
        content="用户习惯使用暗黑模式界面",
        category=MemoryCategory.PREFERENCE,
        memory_type=MemoryLayer.SEMANTIC,
        importance=0.9,
        dedupe_key="pref_theme",
        confidence=0.95,
        metadata={"source": "tool:memory_add"},
    )
    fact_rec = MemoryRecord(
        record_id=new_id("mem"),
        content="用户的开发语言是 Rust 和 Python",
        category=MemoryCategory.FACT,
        memory_type=MemoryLayer.SEMANTIC,
        importance=0.8,
        dedupe_key="fact_lang",
        confidence=0.9,
        metadata={"source": "tool:memory_add"},
    )
    memory.upsert(pref_rec)
    memory.upsert(fact_rec)

    # Verify SSOT (semantic.json) on disk
    assert semantic_json_path.is_file()
    records_1 = json.loads(semantic_json_path.read_text(encoding="utf-8"))
    active_records_1 = [r for r in records_1 if not r.get("deleted")]
    assert len(active_records_1) == 2
    contents_1 = {r["content"] for r in active_records_1}
    assert "用户习惯使用暗黑模式界面" in contents_1
    assert "用户的开发语言是 Rust 和 Python" in contents_1

    # Verify pure projection on MEMORY.md
    proj_1 = memory_path.read_text(encoding="utf-8")
    assert "用户习惯使用暗黑模式界面" in proj_1
    assert "用户的开发语言是 Rust 和 Python" in proj_1
    assert f"<!-- id:{pref_rec.record_id} -->" in proj_1
    assert f"<!-- id:{fact_rec.record_id} -->" in proj_1

    # Verify prompt assembly updated in real time
    persona_1 = persona_from_home(str(home))
    assert "用户习惯使用暗黑模式界面" in persona_1.backstory
    assert "用户的开发语言是 Rust 和 Python" in persona_1.backstory

    # Step 3: Roundtrip idempotency check:
    # Parsing the exact projected markdown should produce 0 deltas
    sync_service = MemoryEditSyncService(memory)
    res_noop = sync_service.apply_markdown_edit(proj_1)
    assert res_noop == {"added": 0, "superseded": 0, "deleted": 0}

    # Step 4: User edits MEMORY.md:
    # - Change preference from '暗黑模式' to '浅色模式' (supersede)
    # - Add a new fact '用户所在时区为 UTC+8' (add)
    # - Retain language fact unchanged
    edited_md = proj_1.replace(
        "用户习惯使用暗黑模式界面",
        "用户习惯使用浅色模式界面",
    )
    edited_md += "\n- 用户所在时区为 UTC+8\n"

    res_edit = sync_service.apply_markdown_edit(edited_md)
    assert res_edit["added"] == 1, "Expected 1 added (new timezone fact)"
    assert res_edit["superseded"] == 1, "Expected 1 superseded (theme changed)"
    assert res_edit["deleted"] == 0

    # Verify semantic.json state after edit
    records_2 = json.loads(semantic_json_path.read_text(encoding="utf-8"))
    active_records_2 = [r for r in records_2 if not r.get("deleted")]
    deleted_records_2 = [r for r in records_2 if r.get("deleted")]
    assert len(active_records_2) == 3
    assert len(deleted_records_2) == 1
    assert deleted_records_2[0]["content"] == "用户习惯使用暗黑模式界面"
    assert deleted_records_2[0]["retired_at_ms"] is not None

    active_contents_2 = {r["content"] for r in active_records_2}
    assert "用户习惯使用浅色模式界面" in active_contents_2
    assert "用户的开发语言是 Rust 和 Python" in active_contents_2
    assert "用户所在时区为 UTC+8" in active_contents_2

    # Verify MEMORY.md updated projection
    proj_2 = memory_path.read_text(encoding="utf-8")
    assert "用户习惯使用浅色模式界面" in proj_2
    assert "用户习惯使用暗黑模式界面" not in proj_2
    assert "用户所在时区为 UTC+8" in proj_2

    # Verify persona_from_home prompt backstory updated
    persona_2 = persona_from_home(str(home))
    assert "用户习惯使用浅色模式界面" in persona_2.backstory
    assert "用户习惯使用暗黑模式界面" not in persona_2.backstory
    assert "用户所在时区为 UTC+8" in persona_2.backstory

    # Step 5: User removes a fact by deleting its bullet in markdown
    # Remove the language fact line completely
    lines = proj_2.splitlines()
    remaining_lines = [line for line in lines if "用户的开发语言是 Rust 和 Python" not in line]
    deleted_fact_md = "\n".join(remaining_lines) + "\n"

    res_delete = sync_service.apply_markdown_edit(deleted_fact_md)
    assert res_delete["deleted"] == 1
    assert res_delete["added"] == 0
    assert res_delete["superseded"] == 0

    # Verify records in semantic.json
    records_3 = json.loads(semantic_json_path.read_text(encoding="utf-8"))
    active_records_3 = [r for r in records_3 if not r.get("deleted")]
    assert len(active_records_3) == 2
    active_contents_3 = {r["content"] for r in active_records_3}
    assert "用户的开发语言是 Rust 和 Python" not in active_contents_3
    assert "用户习惯使用浅色模式界面" in active_contents_3
    assert "用户所在时区为 UTC+8" in active_contents_3

    # Verify prompt backstory has no trace of deleted fact
    persona_3 = persona_from_home(str(home))
    assert "用户的开发语言是 Rust 和 Python" not in persona_3.backstory
    assert "用户习惯使用浅色模式界面" in persona_3.backstory
    assert "用户所在时区为 UTC+8" in persona_3.backstory


def test_standing_backstory_refresh_contains_injected_memory(tmp_path: Path) -> None:
    home = tmp_path / "asst_backstory_test"
    home.mkdir(parents=True, exist_ok=True)
    memory_path = home / "MEMORY.md"

    # When MEMORY.md is written, refresh_standing_backstory captures it
    memory_path.write_text(
        "# 长期记忆\n\n## Facts\n- 核心原则：一源一镜，镜无状态 <!-- id:mem_test -->\n",
        encoding="utf-8",
    )
    backstory = refresh_standing_backstory(str(home), "")
    assert "<!-- INJECTED FILE: MEMORY.md -->" in backstory
    assert "一源一镜，镜无状态" in backstory
    assert "<!-- END INJECTED FILE: MEMORY.md -->" in backstory
