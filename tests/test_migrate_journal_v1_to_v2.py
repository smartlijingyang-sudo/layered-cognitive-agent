"""migrate_journal_v1_to_v2 —— ADR-0065 PR-3 迁移脚本测试。

- v1 → v2 升级补 envelope 字段
- v2 原样透传
- 未知 schema 警告并原样透传
- in-place 覆盖
- 错误 JSON 行报告错误码非零
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _v1_record(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "seq": 1,
        "ts": 1_700_000_000.0,
        "scope": {
            "trace_id": "trace_a",
            "run_id": "run_a",
            "agent_role": "researcher",
            "step": 0,
        },
        "event_type": "AgentRunStarted",
        "data": {"agent_role": "researcher"},
        "parent_seq": None,
    }
    base.update(overrides)
    return base


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def test_migrate_v1_to_v2(tmp_path: Path) -> None:
    input_path = tmp_path / "in.jsonl"
    output_path = tmp_path / "out.jsonl"
    _write_jsonl(input_path, [_v1_record(seq=1), _v1_record(seq=2), _v1_record(seq=3)])

    rc = subprocess.run(  # noqa: S603  # intentional CLI invocation
        [
            sys.executable,
            "scripts/migrate_journal_v1_to_v2.py",
            str(input_path),
            str(output_path),
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
        check=False,
    )
    assert rc.returncode == 0, rc.stderr
    lines = output_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3
    for i, line in enumerate(lines, start=1):
        record = json.loads(line)
        assert record["schema"] == "lca.journal/2"
        assert record["run_seq"] == i
        assert record["event_id"].startswith("evt_")
        assert record["occurred_at"] == 1_700_000_000.0
        assert record["committed_at"] == 1_700_000_000.0
        assert record["descriptor"]["type"] == "AgentRunStarted"
        assert record["causation"]["parent_event_id"] == ""
        assert record["evidence"] == []


def test_migrate_skips_already_v2(tmp_path: Path) -> None:
    """已 v2 的记录原样透传,不重新升级。"""
    input_path = tmp_path / "in.jsonl"
    output_path = tmp_path / "out.jsonl"
    v2_record = {
        "schema": "lca.journal/2",
        "event_id": "evt_existing",
        "run_id": "run_a",
        "run_seq": 1,
        "occurred_at": 1.0,
        "committed_at": 2.0,
        "scope": {"trace_id": "t", "run_id": "run_a", "agent_role": "", "step": 0},
        "causation": {"parent_event_id": "", "links": []},
        "descriptor": {"type": "X", "version": 1, "payload_schema_version": 1},
        "data": {},
        "evidence": [],
    }
    _write_jsonl(input_path, [v2_record])

    rc = subprocess.run(  # noqa: S603  # intentional CLI invocation
        [
            sys.executable,
            "scripts/migrate_journal_v1_to_v2.py",
            str(input_path),
            str(output_path),
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
        check=False,
    )
    assert rc.returncode == 0, rc.stderr
    assert "skipped_v2=1" in rc.stdout

    out = json.loads(output_path.read_text(encoding="utf-8").strip())
    # 原样透传;event_id 保持不变
    assert out["event_id"] == "evt_existing"
    assert out["schema"] == "lca.journal/2"


def test_migrate_in_place(tmp_path: Path) -> None:
    """--in-place 覆盖原文件。"""
    input_path = tmp_path / "in.jsonl"
    _write_jsonl(input_path, [_v1_record(seq=42)])

    rc = subprocess.run(  # noqa: S603  # intentional CLI invocation
        [
            sys.executable,
            "scripts/migrate_journal_v1_to_v2.py",
            "--in-place",
            str(input_path),
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
        check=False,
    )
    assert rc.returncode == 0, rc.stderr
    out = json.loads(input_path.read_text(encoding="utf-8").strip())
    assert out["schema"] == "lca.journal/2"
    assert out["run_seq"] == 42


def test_migrate_missing_file_returns_nonzero(tmp_path: Path) -> None:
    rc = subprocess.run(  # noqa: S603  # intentional CLI invocation
        [
            sys.executable,
            "scripts/migrate_journal_v1_to_v2.py",
            str(tmp_path / "nonexistent.jsonl"),
            str(tmp_path / "out.jsonl"),
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
        check=False,
    )
    assert rc.returncode == 1


def test_migrate_unknown_schema_warns_but_passes_through(tmp_path: Path) -> None:
    input_path = tmp_path / "in.jsonl"
    output_path = tmp_path / "out.jsonl"
    unknown = {"schema": "lca.journal/99", "data": {}}
    _write_jsonl(input_path, [unknown])

    rc = subprocess.run(  # noqa: S603  # intentional CLI invocation
        [
            sys.executable,
            "scripts/migrate_journal_v1_to_v2.py",
            str(input_path),
            str(output_path),
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
        check=False,
    )
    assert rc.returncode == 0
    assert "WARN" in rc.stderr
    out = json.loads(output_path.read_text(encoding="utf-8").strip())
    assert out["schema"] == "lca.journal/99"  # 原样透传


def test_migrate_invalid_json_returns_nonzero(tmp_path: Path) -> None:
    input_path = tmp_path / "in.jsonl"
    output_path = tmp_path / "out.jsonl"
    input_path.write_text("not valid json\n", encoding="utf-8")

    rc = subprocess.run(  # noqa: S603  # intentional CLI invocation
        [
            sys.executable,
            "scripts/migrate_journal_v1_to_v2.py",
            str(input_path),
            str(output_path),
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
        check=False,
    )
    assert rc.returncode == 1
    assert "ERROR" in rc.stderr
