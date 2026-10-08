"""L15 journal format refusal 方向感知测试（ADR-0169 §D3 L15）。

覆盖:
- 三个异常子类的字面契约
- ``check_schema_version`` 方向感知（VersionTooOldError / VersionTooNewError / 通过）
- ``FilesystemJournalStore`` 装载旧/新/未知事件时的方向感知拒绝
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.contracts.observability.journal.format_errors import (
    JournalFormatError,
    UnknownEventTypeError,
    VersionTooNewError,
    VersionTooOldError,
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
    err = VersionTooOldError(schema_version=0, min_supported=MIN_SUPPORTED_VERSION)
    assert isinstance(err, JournalFormatError)
    assert err.schema_version == 0
    assert err.min_supported == MIN_SUPPORTED_VERSION


def test_version_too_new_subclasses_journal_format_error() -> None:
    err = VersionTooNewError(
        schema_version=MAX_SUPPORTED_VERSION + 1, max_supported=MAX_SUPPORTED_VERSION
    )
    assert isinstance(err, JournalFormatError)
    assert err.schema_version == MAX_SUPPORTED_VERSION + 1
    assert err.max_supported == MAX_SUPPORTED_VERSION


def test_unknown_event_type_subclasses_journal_format_error() -> None:
    err = UnknownEventTypeError("MysteryEvent")
    assert isinstance(err, JournalFormatError)
    assert err.event_type == "MysteryEvent"


# ── schema_version 常量 + check_schema_version ──────────


def test_schema_version_constants() -> None:
    assert SCHEMA_VERSION == 2
    assert MIN_SUPPORTED_VERSION == 1
    assert MAX_SUPPORTED_VERSION == 3


def test_version_too_old_raises() -> None:
    with pytest.raises(VersionTooOldError) as excinfo:
        check_schema_version(MIN_SUPPORTED_VERSION - 1)
    assert excinfo.value.schema_version == MIN_SUPPORTED_VERSION - 1
    assert excinfo.value.min_supported == MIN_SUPPORTED_VERSION


def test_version_too_new_raises() -> None:
    with pytest.raises(VersionTooNewError) as excinfo:
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
    with pytest.raises(UnknownEventTypeError) as excinfo:
        FilesystemJournalStore(tmp_path)
    assert excinfo.value.event_type == "MysteryEvent"
    # 文件存在但加载拒绝 —— 不消费任何事件
    assert path.exists()


def test_unknown_event_type_with_ignorable_true_passes(tmp_path: Path) -> None:
    """``ignorable=true`` 时未登记事件不抛 UnknownEventTypeError(reader 边界放行)。"""
    _write_line(tmp_path, _line_with_event_type("MysteryEvent", ignorable=True))
    # 仅断言:不抛 UnknownEventTypeError / VersionToo*
    store = FilesystemJournalStore(tmp_path)
    # 至少读到 0 或 1 行;读到的元素 event_type 仍是 MysteryEvent
    for stamped in store.events():
        assert stamped.event_type == "MysteryEvent"


def test_filesystem_load_rejects_version_too_old(tmp_path: Path) -> None:
    path = _write_line(
        tmp_path,
        _line_with_event_type("AgentRunStarted", schema_version=MIN_SUPPORTED_VERSION - 1),
    )
    with pytest.raises(VersionTooOldError):
        FilesystemJournalStore(tmp_path)
    assert path.exists()


def test_filesystem_load_rejects_version_too_new(tmp_path: Path) -> None:
    path = _write_line(
        tmp_path,
        _line_with_event_type("AgentRunStarted", schema_version=MAX_SUPPORTED_VERSION + 1),
    )
    with pytest.raises(VersionTooNewError):
        FilesystemJournalStore(tmp_path)
    assert path.exists()


def test_filesystem_load_accepts_known_event_at_current_version(tmp_path: Path) -> None:
    payload = _line_with_event_type("AgentRunStarted", schema_version=SCHEMA_VERSION)
    # StampedEvent 实际绑定 AgentRunStarted 类，故 event_type 与类一致
    _write_line(tmp_path, payload)
    store = FilesystemJournalStore(tmp_path)
    assert len(store.events()) == 1
    assert store.events()[0].event_type == "AgentRunStarted"


def _encoded_event(seq: int) -> bytes:
    payload = _line_with_event_type("AgentRunStarted")
    payload["seq"] = seq
    return (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")


def test_filesystem_load_rejects_corrupt_complete_middle_line(tmp_path: Path) -> None:
    path = tmp_path / "default-run.spine.jsonl"
    path.write_bytes(_encoded_event(1) + b"{broken json}\n" + _encoded_event(2))

    with pytest.raises(JournalFormatError, match=r"line 2.*invalid JSON"):
        FilesystemJournalStore(tmp_path)


def test_filesystem_load_rejects_sequence_gap(tmp_path: Path) -> None:
    path = tmp_path / "default-run.spine.jsonl"
    path.write_bytes(_encoded_event(1) + _encoded_event(3))

    with pytest.raises(JournalFormatError, match=r"line 2.*expected seq=2.*got seq=3"):
        FilesystemJournalStore(tmp_path)


def test_filesystem_load_repairs_only_unterminated_partial_tail(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "default-run.spine.jsonl"
    complete = _encoded_event(1)
    path.write_bytes(complete + b'{"seq":2,"event_type":"AgentRunStarted"')

    store = FilesystemJournalStore(tmp_path)
    try:
        assert [event.seq for event in store.events()] == [1]
        assert path.read_bytes() == complete
        assert any(
            "repaired trailing partial journal record" in record.message
            for record in caplog.records
        )
    finally:
        store.close()


def test_filesystem_load_reports_read_failure(tmp_path: Path, monkeypatch) -> None:
    path = _write_line(tmp_path, _line_with_event_type("AgentRunStarted"))
    original_read_bytes = Path.read_bytes
    original_read_text = Path.read_text

    def fail_read_bytes(self: Path) -> bytes:
        if self == path:
            raise PermissionError("permission denied")
        return original_read_bytes(self)

    def fail_read_text(self: Path, *args, **kwargs) -> str:
        if self == path:
            raise PermissionError("permission denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)
    monkeypatch.setattr(Path, "read_text", fail_read_text)

    with pytest.raises(JournalFormatError, match="permission denied"):
        FilesystemJournalStore(tmp_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scope", "not-an-object"),
        ("scope", []),
        ("scope", None),
        ("data", []),
        ("data", None),
    ],
)
def test_filesystem_load_reports_reconstruction_failure(
    tmp_path: Path, field: str, value: object
) -> None:
    payload = _line_with_event_type("AgentRunStarted")
    payload[field] = value
    _write_line(tmp_path, payload)

    with pytest.raises(JournalFormatError, match=r"line 1"):
        FilesystemJournalStore(tmp_path)


@pytest.mark.parametrize("tail", [b"{broken json}", b" \t "])
def test_filesystem_load_rejects_corrupt_unterminated_final_line(
    tmp_path: Path, tail: bytes
) -> None:
    path = tmp_path / "default-run.spine.jsonl"
    corrupt = _encoded_event(1) + tail
    path.write_bytes(corrupt)

    with pytest.raises(JournalFormatError, match=r"line 2.*invalid JSON"):
        FilesystemJournalStore(tmp_path)

    assert path.read_bytes() == corrupt
