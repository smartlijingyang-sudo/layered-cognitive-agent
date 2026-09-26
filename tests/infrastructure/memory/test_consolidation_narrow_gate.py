"""ADR-0249: dream promotes once and does not rewrite USER.md on the second pass."""

from __future__ import annotations

import json
from pathlib import Path

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.memory.episode import EpisodeFact, ResidualClass
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.dream import run_dream
from lca.infrastructure.memory.episode_buffer import EpisodeBuffer

_NOW = 1_700_000_000_000
_RENDER = "# 用户画像\n\n## 偏好\n- 用户偏好：详细\n\n"


def _pref(fact_id: str, trace_id: str, content: str, observed_at_ms: int) -> EpisodeFact:
    return EpisodeFact(
        fact_id=fact_id,
        dedupe_key="preference:verbosity",
        category=MemoryCategory.PREFERENCE,
        content=content,
        residual=ResidualClass.instruction,
        explicit_user_authority=False,
        source_trace_id=trace_id,
        observed_at_ms=observed_at_ms,
    )


def test_dream_writes_preimage_once_and_does_not_duplicate_rows(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    home.mkdir()
    (home / "USER.md").write_text("old\n", encoding="utf-8")
    buffer = EpisodeBuffer(home)
    buffer.append(_pref("ep_a", "t1", "用户偏好：简洁", _NOW))
    buffer.append(_pref("ep_b", "t2", "用户偏好：详细", _NOW + 5))

    def _render(_records: object) -> str:
        return _RENDER

    def _backfill(assistant_id: str, records: list[object]) -> None:
        assert assistant_id == home.name
        assert any(getattr(record, "content", None) == "用户偏好：详细" for record in records)
        (home / "USER.md").write_text(_RENDER, encoding="utf-8")

    run_dream(home, now_ms=_NOW, backfill=_backfill, render=_render)

    preimage = home / "revisions" / f"user-md-preimage-{_NOW}.md"
    assert preimage.read_text(encoding="utf-8") == "old\n"
    assert (home / "USER.md").read_text(encoding="utf-8") == _RENDER
    semantic = json.loads((home / "memory" / "semantic.json").read_text(encoding="utf-8"))
    active = [row for row in semantic if not row.get("deleted")]
    assert len(active) == 1
    assert active[0]["content"] == "用户偏好：详细"
    assert len(AssistantMemory(home).query(MemoryLayer.SEMANTIC)) == 1

    run_dream(home, now_ms=_NOW, backfill=_backfill, render=_render)

    semantic_again = json.loads((home / "memory" / "semantic.json").read_text(encoding="utf-8"))
    active_again = [row for row in semantic_again if not row.get("deleted")]
    assert len(active_again) == 1
    assert len(list((home / "revisions").glob("user-md-preimage-*.md"))) == 1
    assert preimage.read_text(encoding="utf-8") == "old\n"
