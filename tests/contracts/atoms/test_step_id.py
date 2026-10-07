"""RA-025: ``step-{n:03d}`` step_id 约定单源（``lca.contracts.atoms.ids``）。

约定第一次有直接测试面：``step-NNN`` 字节形态是 fold key / hook key /
reasoner key 匹配的依据，四处调用点（hook / llm_call / nodes/think /
reasoner）必须派生同一字符串。
"""

from __future__ import annotations

from types import SimpleNamespace

from lca.contracts.atoms.ids.ids import step_id_for, step_id_from_cursor


def test_step_id_for_formats_zero_padded() -> None:
    assert step_id_for(3) == "step-003"


def test_step_id_for_zero_and_large() -> None:
    assert step_id_for(0) == "step-000"
    assert step_id_for(42) == "step-042"


def test_step_id_from_cursor_none_falls_back() -> None:
    assert step_id_from_cursor(None, "t") == "step-unknown-t"


def test_step_id_from_cursor_reads_snapshot_step_index() -> None:
    cursor = SimpleNamespace(snapshot=SimpleNamespace(step_index=4))
    assert step_id_from_cursor(cursor, "t") == "step-005"


def test_step_id_from_cursor_broken_snapshot_falls_back() -> None:
    cursor = SimpleNamespace(snapshot=SimpleNamespace(step_index=None))
    assert step_id_from_cursor(cursor, "tpl") == "step-unknown-tpl"


def test_step_id_from_cursor_missing_snapshot_falls_back() -> None:
    assert step_id_from_cursor(SimpleNamespace(), "tpl") == "step-unknown-tpl"
