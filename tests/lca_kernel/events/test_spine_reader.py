"""SpineReader 入口(PR-4 收口)单测 —— ADR-0183 §3.8 + I-FW-SSOT-1。

SpineReader 是事实链唯一读入口:
- :meth:`locate` 解析并校验 spine 路径(无 legacy 兜底,缺则抛);
- :meth:`events` 逐行反序列化为 :class:`SpineEventRecord`;
- :meth:`read_dicts` 逐行原样产出原始 dict(供旧 reader / deriver 透传)。

PR-4 收口:旧 ``events.jsonl`` layout 不再被任何 reader 接受;这两条
单测锁死 I-FW-SSOT-1 reader SSOT。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca_kernel.events.reader import SpineFileMissingError, SpineReader


def test_locate_returns_canonical_spine_path(tmp_path: Path) -> None:
    """``SpineReader.locate`` 解析 ``<run_id>.spine.jsonl`` 物理路径。"""
    run_id = "run_locate_001"
    spine_path = tmp_path / f"{run_id}.spine.jsonl"
    spine_path.write_text("{}\n", encoding="utf-8")
    assert SpineReader.locate(run_id, root=tmp_path) == spine_path


def test_locate_raises_when_spine_missing(tmp_path: Path) -> None:
    """``SpineReader.locate`` 缺 spine 文件时抛 :class:`SpineFileMissingError`。

    PR-4 收口:不再 silent fallback 到 ``events.jsonl``;fail-loud 让
    caller 走诊断路径。
    """
    run_id = "run_locate_002"
    # 仅有 legacy 文件(PR-4 收口:不再被 locate 接受)
    (tmp_path / "events.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(SpineFileMissingError) as excinfo:
        SpineReader.locate(run_id, root=tmp_path)
    assert run_id in str(excinfo.value)
    assert "events.jsonl" not in str(excinfo.value)


def test_locate_does_not_consult_legacy_layout(tmp_path: Path) -> None:
    """``SpineReader.locate`` 在仅有 ``events.jsonl`` 时必须抛(legacy 已退役)。"""
    run_id = "run_locate_003"
    legacy = tmp_path / "events.jsonl"
    legacy.write_text("{}\n", encoding="utf-8")
    with pytest.raises(SpineFileMissingError):
        SpineReader.locate(run_id, root=tmp_path)
    assert legacy.exists(), "legacy 文件不应被 locate 删除"


def test_read_dicts_yields_raw_dict_per_line(tmp_path: Path) -> None:
    """``read_dicts`` 逐行产出 raw dict(供旧 reader / deriver 透传)。"""
    run_id = "run_dicts_001"
    spine_path = tmp_path / f"{run_id}.spine.jsonl"
    spine_path.write_text(
        json.dumps({"event_id": "evt_1", "execution_point": "kernel.run.start"}) + "\n"
        + json.dumps({"event_id": "evt_2", "execution_point": "kernel.run.stop"}) + "\n",
        encoding="utf-8",
    )
    records = list(SpineReader(run_id, path=spine_path).read_dicts())
    assert len(records) == 2
    assert records[0]["event_id"] == "evt_1"
    assert records[1]["execution_point"] == "kernel.run.stop"


def test_read_dicts_skips_corrupted_lines(tmp_path: Path) -> None:
    """``read_dicts`` 损坏行 log + skip,不 raise。"""
    run_id = "run_dicts_002"
    spine_path = tmp_path / f"{run_id}.spine.jsonl"
    spine_path.write_text(
        json.dumps({"event_id": "ok_1"}) + "\n"
        + "this is not json\n"
        + json.dumps({"event_id": "ok_2"}) + "\n",
        encoding="utf-8",
    )
    records = list(SpineReader(run_id, path=spine_path).read_dicts())
    assert [r["event_id"] for r in records] == ["ok_1", "ok_2"]


def test_read_dicts_skips_blank_lines(tmp_path: Path) -> None:
    """``read_dicts`` 空行静默跳过。"""
    run_id = "run_dicts_003"
    spine_path = tmp_path / f"{run_id}.spine.jsonl"
    spine_path.write_text(
        json.dumps({"event_id": "ok_1"}) + "\n\n"
        + json.dumps({"event_id": "ok_2"}) + "\n",
        encoding="utf-8",
    )
    records = list(SpineReader(run_id, path=spine_path).read_dicts())
    assert [r["event_id"] for r in records] == ["ok_1", "ok_2"]


def test_read_dicts_skips_non_dict_lines(tmp_path: Path) -> None:
    """``read_dicts`` 非对象行(JSON 数组 / 标量)静默跳过。"""
    run_id = "run_dicts_004"
    spine_path = tmp_path / f"{run_id}.spine.jsonl"
    spine_path.write_text(
        json.dumps({"event_id": "ok_1"}) + "\n"
        + json.dumps([1, 2, 3]) + "\n"  # 非 dict
        + "42\n"  # 标量
        + json.dumps({"event_id": "ok_2"}) + "\n",
        encoding="utf-8",
    )
    records = list(SpineReader(run_id, path=spine_path).read_dicts())
    assert [r["event_id"] for r in records] == ["ok_1", "ok_2"]


def test_read_dicts_missing_file_yields_nothing(tmp_path: Path) -> None:
    """``read_dicts`` 缺文件 log + return empty iterator。"""
    run_id = "run_dicts_005"
    spine_path = tmp_path / f"{run_id}.spine.jsonl"  # never created
    records = list(SpineReader(run_id, path=spine_path).read_dicts())
    assert records == []


__all__ = [
    "test_locate_does_not_consult_legacy_layout",
    "test_locate_raises_when_spine_missing",
    "test_locate_returns_canonical_spine_path",
    "test_read_dicts_missing_file_yields_nothing",
    "test_read_dicts_skips_blank_lines",
    "test_read_dicts_skips_corrupted_lines",
    "test_read_dicts_skips_non_dict_lines",
    "test_read_dicts_yields_raw_dict_per_line",
]
