"""L15 journal format refusal 方向感知测试（ADR-0169 §D3 L15）。

覆盖:
- 三个异常子类的字面契约
- ``check_schema_version`` 方向感知（VersionTooOld / VersionTooNew / 通过）
- ``FilesystemJournalStore`` 装载旧/新/未知事件时的方向感知拒绝
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.contracts.observability.journal_format_errors import (
    JournalFormatError,
    UnknownEventType,
    VersionTooNew,
    VersionTooOld,
)
from lca.infrastructure.observability.journal.backends.filesystem import (
    FilesystemJournalStore,
)
from lca.infrastructure.observability.journal.schema_version import (
    MAX_SUPPORTED_VERSION,
    MIN_SUPPORTED_VERSION,
    SCHEMA_VERSION,
    check_schema_version,
)

# ── 异常子类契约 ──────────────────────────────────────


def test_version_too_old_subclasses_journal_format_error() -> None:
    err = VersionTooOld(schema_version=0, min_supported=MIN_SUPPORTED_VERSION)
    assert isinstance(err, JournalFormatError)
    assert err.schema_version == 0
    assert err.min_supported == MIN_SUPPORTED_VERSION


def test_version_too_new_subclasses_journal_format_error() -> None:
    err = VersionTooNew(
        schema_version=MAX_SUPPORTED_VERSION + 1, max_supported=MAX_SUPPORTED_VERSION
    )
    assert isinstance(err, JournalFormatError)
    assert err.schema_version == MAX_SUPPORTED_VERSION + 1
    assert err.max_supported == MAX_SUPPORTED_VERSION


def test_unknown_event_type_subclasses_journal_format_error() -> None:
    err = UnknownEventType("MysteryEvent")
    assert isinstance(err, JournalFormatError)
    assert err.event_type == "MysteryEvent"


# ── schema_version 常量 + check_schema_version ──────────


def test_schema_version_constants() -> None:
    assert SCHEMA_VERSION == 2
    assert MIN_SUPPORTED_VERSION == 1
    assert MAX_SUPPORTED_VERSION == 3


def test_version_too_old_raises() -> None:
    with pytest.raises(VersionTooOld) as excinfo:
        check_schema_version(MIN_SUPPORTED_VERSION - 1)
    assert excinfo.value.schema_version == MIN_SUPPORTED_VERSION - 1
    assert excinfo.value.min_supported == MIN_SUPPORTED_VERSION


def test_version_too_new_raises() -> None:
    with pytest.raises(VersionTooNew) as excinfo:
        check_schema_version(MAX_SUPPORTED_VERSION + 1)
    assert excinfo.value.schema_version == MAX_SUPPORTED_VERSION + 1
    assert excinfo.value.max_supported == MAX_SUPPORTED_VERSION


def test_version_in_range_passes() -> None:
    # 区间所有版本（含端点）都不抛
    for v in range(MIN_SUPPORTED_VERSION, MAX_SUPPORTED_VERSION + 1):
        check_schema_version(v)  # 不抛即通过


# ── FilesystemJournalStore 装载行为 ─────────────────────


def _write_line(tmp_path: Path, payload: dict) -> Path:
    # PR-4 收口:FilesystemJournalStore 只识别 spine 命名;旧 events.jsonl layout 已下线。
    # default-run + tmp_path 根 → 派生文件名 = default-run.spine.jsonl。
    path = tmp_path / "default-run.spine.jsonl"
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _line_with_event_type(
    event_type: str,
    *,
    schema_version: int | None = SCHEMA_VERSION,
    ignorable: bool = False,
) -> dict:
    payload: dict = {
        "seq": 1,
        "ts": 1000.0,
        "event_type": event_type,
        "scope": {"trace_id": "t", "run_id": "r"},
        "data": {} if not ignorable else {"ignorable": True},
        "parent_seq": None,
    }
    if schema_version is not None:
        payload["schema_version"] = schema_version
    return payload


def test_unknown_event_type_with_ignorable_false_raises(tmp_path: Path) -> None:
    path = _write_line(tmp_path, _line_with_event_type("MysteryEvent", ignorable=False))
    with pytest.raises(UnknownEventType) as excinfo:
        FilesystemJournalStore(tmp_path)
    assert excinfo.value.event_type == "MysteryEvent"
    # 文件存在但加载拒绝 —— 不消费任何事件
    assert path.exists()


def test_unknown_event_type_with_ignorable_true_passes(tmp_path: Path) -> None:
    """``ignorable=true`` 时未登记事件不抛 UnknownEventType(reader 边界放行)。"""
    _write_line(tmp_path, _line_with_event_type("MysteryEvent", ignorable=True))
    # 仅断言:不抛 UnknownEventType / VersionToo*
    store = FilesystemJournalStore(tmp_path)
    # 至少读到 0 或 1 行;读到的元素 event_type 仍是 MysteryEvent
    for stamped in store.events():
        assert stamped.event_type == "MysteryEvent"


def test_filesystem_load_rejects_version_too_old(tmp_path: Path) -> None:
    path = _write_line(
        tmp_path,
        _line_with_event_type("AgentRunStarted", schema_version=MIN_SUPPORTED_VERSION - 1),
    )
    with pytest.raises(VersionTooOld):
        FilesystemJournalStore(tmp_path)
    assert path.exists()


def test_filesystem_load_rejects_version_too_new(tmp_path: Path) -> None:
    path = _write_line(
        tmp_path,
        _line_with_event_type("AgentRunStarted", schema_version=MAX_SUPPORTED_VERSION + 1),
    )
    with pytest.raises(VersionTooNew):
        FilesystemJournalStore(tmp_path)
    assert path.exists()


def test_filesystem_load_accepts_known_event_at_current_version(tmp_path: Path) -> None:
    payload = _line_with_event_type("AgentRunStarted", schema_version=SCHEMA_VERSION)
    # StampedEvent 实际绑定 AgentRunStarted 类，故 event_type 与类一致
    _write_line(tmp_path, payload)
    store = FilesystemJournalStore(tmp_path)
    assert len(store.events()) == 1
    assert store.events()[0].event_type == "AgentRunStarted"
