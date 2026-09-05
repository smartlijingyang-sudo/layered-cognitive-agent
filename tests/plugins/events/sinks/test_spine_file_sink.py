"""spine_file_sink 端到端（ADR-0181 PR-8 shim；record 入口 ADR-0183 PR-5）。

record 构造走 build_record() 单一入口；落盘走 SpineSink SSOT 路径；
字节布局 = SpineEventRecord.to_dict() 10 键（sort_keys；含 ADR-0183 §3.9 trace_id）。
run_id 逐事件从 ref.event_id 的 Session 投递形态 "{session.id}:{seq}" 推导，
落 <run_dir>/<run_id>.spine.jsonl；无 run 上下文上抛，不落默认文件。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.infrastructure.persistence.run_buffer_registry import RunWriteBehindRegistry
from lca.plugins.events.sinks.spine_file_sink.sink import SpineFileSink, _run_id_of
from lca.plugins.session.runtime.bus_facade import SessionBusFacade
from lca.plugins.session.runtime.session import Session
from lca_kernel.events import EventRef
from lca_kernel.events.payloads import SpineEventPayload
from lca_kernel.events.persistence import PersistenceObserver


@pytest.fixture(autouse=True)
def _isolate_write_behind_singletons() -> None:
    PersistenceObserver.reset_singleton()
    RunWriteBehindRegistry.reset_singleton()
    yield
    PersistenceObserver.reset_singleton()
    RunWriteBehindRegistry.reset_singleton()

_RECORD_KEYS = {
    "event_id",
    "category",
    "execution_point",
    "channel",
    "payload",
    "ts",
    "causation_id",
    "prev_event_hash",
    "event_hash",
    "trace_id",
}


def _ref(event_id: str = "run-test-1:0") -> EventRef:
    return EventRef(
        event_id=event_id,
        category="spine.cognition.brain.perceive.start",
        trace_id="",
        ts=1725350000.0,
        persisted=False,
        subscriber_count=0,
    )


def _payload() -> SpineEventPayload:
    return SpineEventPayload(
        execution_point="brain.perceive.start",
        channel="fact",
        payload={"state_id": "s1"},
    )


def test_spine_file_sink_writes_ten_key_record(tmp_path: Path) -> None:
    """build_record 单一入口落盘：10 键 SSOT 布局（含 trace_id）+ sort_keys 序列化。"""
    sink = SpineFileSink(run_dir=tmp_path)
    sink(_payload(), _ref("run-test-1:0"))
    sink.flush()

    target = tmp_path / "run-test-1.spine.jsonl"
    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert set(record) == _RECORD_KEYS
    assert record["event_id"] == "run-test-1:0"
    assert record["category"] == "spine.cognition.brain.perceive.start"
    assert record["execution_point"] == "brain.perceive.start"
    assert record["channel"] == "fact"
    assert record["payload"] == {"state_id": "s1"}
    assert record["causation_id"] is None
    assert record["prev_event_hash"] is None
    assert record["event_hash"] is None
    # build_record() 当前不透传 ref.trace_id；键必在、值为 null。
    assert record["trace_id"] is None
    assert lines[0] == json.dumps(record, sort_keys=True)


def test_spine_file_sink_routes_each_run_to_own_file(tmp_path: Path) -> None:
    """事件按 event_id 前缀的 run_id 分文件；不再汇进单一 default-run 文件。"""
    sink = SpineFileSink(run_dir=tmp_path)
    sink(_payload(), _ref("run-a:0"))
    sink(_payload(), _ref("run-b:0"))
    sink(_payload(), _ref("run-a:1"))
    sink.flush()

    run_a = (tmp_path / "run-a.spine.jsonl").read_text(encoding="utf-8").splitlines()
    run_b = (tmp_path / "run-b.spine.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["event_id"] for line in run_a] == ["run-a:0", "run-a:1"]
    assert [json.loads(line)["event_id"] for line in run_b] == ["run-b:0"]
    assert not (tmp_path / "default-run.spine.jsonl").exists()


def test_spine_file_sink_observes_real_session_run_id(tmp_path: Path) -> None:
    """经 SessionBusFacade 全链：文件取 session.id，不产生 default-run 文件。"""
    session = Session("run-e2e-42")
    facade = SessionBusFacade(session)
    sink = SpineFileSink(run_dir=tmp_path)
    facade.observe(SpineFileSink, sink)

    facade.append(_payload(), producer=object())
    sink.flush()

    target = tmp_path / "run-e2e-42.spine.jsonl"
    assert target.exists()
    lines = target.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["event_id"] == "run-e2e-42:0"
    assert not (tmp_path / "default-run.spine.jsonl").exists()


@pytest.mark.parametrize("event_id", ["evt_no_colon", ":3", "run-x:"])
def test_spine_file_sink_raises_without_run_context(tmp_path: Path, event_id: str) -> None:
    """无 run 上下文 fail-loud：上抛且不落任何文件（投递侧 contained + 记日志）。"""
    sink = SpineFileSink(run_dir=tmp_path)
    with pytest.raises(ValueError, match="run_id"):
        sink(_payload(), _ref(event_id))
    assert list(tmp_path.iterdir()) == []


def test_spine_file_sink_append_record_routes_by_record_event_id(tmp_path: Path) -> None:
    """SinkBackend.append 与 __call__ 同源：run_id 取 record.event_id 前缀。"""
    from lca_kernel.events.spine_runtime import build_record

    sink = SpineFileSink(run_dir=tmp_path)
    sink.append(build_record(_payload(), _ref("run-rec:7")))

    target = tmp_path / "run-rec.spine.jsonl"
    assert json.loads(target.read_text(encoding="utf-8"))["event_id"] == "run-rec:7"


def test_spine_file_sink_rejects_non_spine_payload(tmp_path: Path) -> None:
    """非 SpineEventPayload 直接上抛 TypeError（无静默兜底）。"""
    sink = SpineFileSink(run_dir=tmp_path)
    with pytest.raises(TypeError, match="SpineEventPayload"):
        sink(object(), _ref("run-test-1:0"))


def test_spine_file_sink_close_blocks_further_writes(tmp_path: Path) -> None:
    """close 后 append / flush 上抛（SinkBackend close 契约）。"""
    sink = SpineFileSink(run_dir=tmp_path)
    sink(_payload(), _ref("run-test-1:0"))
    sink.close()
    with pytest.raises(RuntimeError, match="已关闭"):
        sink(_payload(), _ref("run-test-1:1"))
    with pytest.raises(RuntimeError, match="已关闭"):
        sink.flush()


def test_spine_file_sink_default_path_lands_under_traces_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_dir 缺省时落 ``traces/runs/<run_id>/<run_id>.spine.jsonl``。

    回归锁:缺省曾退回 ``Path.cwd()``,仓库根散落游离镜像文件。
    """
    monkeypatch.chdir(tmp_path)
    sink = SpineFileSink()
    sink(_payload(), _ref("run-default-path:0"))
    sink.flush()

    target = tmp_path / "traces" / "runs" / "run-default-path" / "run-default-path.spine.jsonl"
    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8"))["event_id"] == "run-default-path:0"
    assert not (tmp_path / "run-default-path.spine.jsonl").exists()


@pytest.mark.parametrize(
    ("event_id", "expected"),
    [("run-1:0", "run-1"), ("ns:run-2:17", "ns:run-2"), ("run-x:3", "run-x")],
)
def test_run_id_of_parses_session_delivery_shape(event_id: str, expected: str) -> None:
    """'{session.id}:{seq}' 反解；rpartition 容忍 run id 自带冒号。"""
    assert _run_id_of(event_id) == expected

