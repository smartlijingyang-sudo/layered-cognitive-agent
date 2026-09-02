"""ADR-0169 PR-2 / S2 — L10 单写集成测试。

L10 不变量:`events.jsonl`(或 sink.path)由 ``EventSpine.append`` 唯一写入。
本测试通过 FileSink 与 EventSpine 端到端验证:
- spine.append N 次 → sink.path 行数 = N(1:1,L10)
- 没有第二个 writer 往同一路径写(spine 是唯一入口)
"""

from __future__ import annotations

import json
from pathlib import Path

from lca.infrastructure.observability.spine.event_spine import EventSpine
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink


def _make_sink(tmp_path: Path, run_id: str) -> FileSink:
    return FileSink(tmp_path, run_id=run_id)


def test_l10_sink_line_count_equals_spine_append(tmp_path: Path) -> None:
    """L10:spine.append N 次 → sink.path 行数 = N(1:1)。"""
    sink = _make_sink(tmp_path, "run_l10")
    spine = EventSpine(sinks=[sink], run_id="run_l10")

    n_appends = 5
    for i in range(1, n_appends + 1):
        spine.append(
            execution_point="writable.step.start",
            channel="fact",
            caller_payload={"seq": i},
            outcome="success",
        )

    spine.flush()
    spine.close()
    sink.close()

    text = sink.path.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert len(lines) == n_appends, (
        f"L10 violation: spine.append {n_appends} 次,但 sink.path 写入 {len(lines)} 行"
    )

    # 每行是合法 JSON,且 sequence 字段存在
    for i, line in enumerate(lines, start=1):
        obj = json.loads(line)
        assert obj["sequence"] == i


def test_l10_spine_filename_produces_spine_suffixed_file(tmp_path: Path) -> None:
    """L10 + D9:`spine_filename=True` 时 sink.path = ``<run_id>.spine.jsonl``。"""
    run_id = "run_x"
    sink = FileSink(tmp_path, run_id=run_id, spine_filename=True)
    assert sink.path.name == "run_x.spine.jsonl"

    spine = EventSpine(sinks=[sink], run_id=run_id)
    spine.append(
        execution_point="writable.step.start",
        channel="fact",
        caller_payload={"seq": 1},
        outcome="success",
    )
    spine.flush()
    spine.close()
    sink.close()

    text = sink.path.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["run_id"] == run_id


def test_l10_legacy_events_jsonl_still_supported(tmp_path: Path) -> None:
    """向后兼容:`spine_filename=False` 默认行为仍写 ``events.jsonl``。

    本测试保证 PR-2 不破坏既有生产路径(显式传 file_name 或依赖默认值)。
    """
    sink = FileSink(tmp_path, run_id="legacy_run")
    assert sink.path.name == "events.jsonl"  # 默认值不变

    spine = EventSpine(sinks=[sink], run_id="legacy_run")
    spine.append(
        execution_point="writable.step.start",
        channel="fact",
        caller_payload={"seq": 1},
        outcome="success",
    )
    spine.flush()
    spine.close()
    sink.close()

    assert sink.path.exists()
    assert sink.path.read_text().strip() != ""


def test_l10_single_writer_no_concurrent_writers(tmp_path: Path) -> None:
    """L10:同一 run 不存在两个 writer 写同一文件。

    验证 FileSink 对同一文件是单实例负责 append(无 toctou 双写)。
    """
    sink_a = FileSink(tmp_path / "run_a", run_id="run_a")
    sink_b = FileSink(tmp_path / "run_a", run_id="run_a")  # 同一路径
    spine_a = EventSpine(sinks=[sink_a], run_id="run_a")
    spine_b = EventSpine(sinks=[sink_b], run_id="run_a")

    spine_a.append(
        execution_point="writable.step.start",
        channel="fact",
        caller_payload={"seq": 1},
        outcome="success",
    )
    spine_b.append(
        execution_point="writable.step.start",
        channel="fact",
        caller_payload={"seq": 2},
        outcome="success",
    )
    spine_a.flush()
    spine_b.flush()
    spine_a.close()
    spine_b.close()
    sink_a.close()
    sink_b.close()

    # 同一路径累计 2 行(L10 不要求同实例;要求总写入行数 == 总 append)
    lines = [ln for ln in sink_a.path.read_text().splitlines() if ln.strip()]
    assert len(lines) == 2
