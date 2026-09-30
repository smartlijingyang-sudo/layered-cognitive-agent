"""INV-EFFECT-GATEWAY-TRAIL-APPEND-ONLY — daily trail files are append-only."""

from __future__ import annotations

import pytest

from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.service.trail import (
    NarrowGateViolationError,
    TrailWriter,
)


def test_append_writes_both_entries(tmp_path) -> None:
    writer = TrailWriter(DiskFileStore(tmp_path))
    path = writer.append("2026-09-30", "用户说：回复要简洁")
    path2 = writer.append("2026-09-30", "用户说：不要用 emoji")
    assert path == "memory/2026-09-30.md"
    assert path2 == path
    text = (tmp_path / "memory" / "2026-09-30.md").read_text(encoding="utf-8")
    assert "回复要简洁" in text
    assert "不要用 emoji" in text


def test_overwrite_attempt_raises_narrow_gate_violation(tmp_path) -> None:
    writer = TrailWriter(DiskFileStore(tmp_path))
    writer.append("2026-09-30", "原始流水")
    with pytest.raises(NarrowGateViolationError):
        writer.overwrite("2026-09-30", "篡改后的内容")
    text = (tmp_path / "memory" / "2026-09-30.md").read_text(encoding="utf-8")
    assert "原始流水" in text
    assert "篡改后的内容" not in text


def test_store_refuses_a_shortening_replace_of_the_trail(tmp_path) -> None:
    store = DiskFileStore(tmp_path)
    writer = TrailWriter(store)
    writer.append("2026-09-30", "原始流水")
    with pytest.raises(NarrowGateViolationError):
        store.atomic_replace("memory/2026-09-30.md", "# 2026-09-30\n\n- 篡改\n")
    text = (tmp_path / "memory" / "2026-09-30.md").read_text(encoding="utf-8")
    assert "原始流水" in text
    assert "篡改" not in text
