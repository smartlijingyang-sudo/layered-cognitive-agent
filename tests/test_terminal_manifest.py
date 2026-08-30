"""终态封存测试 —— ADR-0065 §一 / §六 / PR-11。

``_record_terminal_materialization`` 在 run 进入终态后写:
- ``<run_id>/manifest.json`` —— RunManifest + doctor_report merged in extra
- ``traces/latest.json`` —— 原子指针,指向该 run

本测试不依赖 boot / plugin / LLM,只验证:
1. manifest.json 落盘且字段合规
2. doctor_report 合并进 extra(向后兼容 doctor.v2 schema)
3. latest.json 原子更新(临时文件 + rename)
4. 异常路径下不抛(只记日志)
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from gateway.runs.doctor import diagnose
from gateway.runs.execute import _record_terminal_materialization
from gateway.runs.observability.identity import parse_agent_ref
from gateway.runs.session.session import RunSession, RunStatus
from lca.infrastructure.observability.journal.engine.journal_io import JOURNAL_SCHEMA_VERSION
from lca.infrastructure.observability.journal.stream.live_tail import LiveTail
from lca.infrastructure.observability.run_locator_fs import FilesystemRunLocator


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _row(seq: int, event_type: str, event: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": JOURNAL_SCHEMA_VERSION,
        "seq": seq,
        "ts": float(seq),
        "scope": {"trace_id": "t", "run_id": "run_x", "agent_role": "agt_x", "step": 0},
        "event_type": event_type,
        "event": event,
    }


def _make_session(*, run_id: str, jsonl_path: Path, status: RunStatus) -> RunSession:
    locator = FilesystemRunLocator(root=jsonl_path.parent.parent.parent)
    return RunSession(
        run_id=run_id,
        trace_id="trace_x",
        jsonl_path=jsonl_path,
        tail=LiveTail(),
        question="q",
        user_text="q",
        mode="solo",
        agent=parse_agent_ref({"id": "solo", "name": "助手"}),
        status=status,
        started_at=1000.0,
        closed_at=1100.0,
        locator=locator,
    )


class TerminalManifestWritesPerRun(unittest.TestCase):
    """终态 manifest.json + latest.json 落地。"""

    def test_manifest_written_with_run_id_and_terminal_event_seq(self) -> None:
        with self._fresh_root() as root:
            run_id = "run_terminal01"
            jsonl_path = root / "runs" / run_id / "journal.jsonl"
            _write_jsonl(
                jsonl_path,
                [
                    _row(
                        1,
                        "AgentRunStarted",
                        {"agent_role": "agt_x", "objective": "q"},
                    ),
                    _row(
                        2,
                        "AgentRunFinished",
                        {"agent_role": "agt_x", "ok": True},
                    ),
                ],
            )
            session = _make_session(
                run_id=run_id, jsonl_path=jsonl_path, status=RunStatus.COMPLETED
            )

            _record_terminal_materialization(session)

            manifest_path = root / "runs" / run_id / "manifest.json"
            self.assertTrue(manifest_path.exists(), "manifest.json must exist")
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "lca.run_manifest/1")
            self.assertEqual(payload["run_id"], run_id)
            # ADR-0096 I7: derived view holds journal seq, not hard event_id.
            self.assertEqual(payload["terminal_event_seq"], 2)
            self.assertNotIn("terminal_event_id", payload)
            self.assertEqual(payload["ledger_high_watermark"], 2)
            self.assertNotEqual(payload["ledger_summary"], "")
            self.assertEqual(payload["started_at"], 1000.0)
            self.assertEqual(payload["closed_at"], 1100.0)
            self.assertIn("doctor_report", payload["extra"])
            self.assertEqual(payload["extra"]["doctor_report"]["schema"], "doctor.v2")

    def test_latest_json_atomically_written(self) -> None:
        with self._fresh_root() as root:
            run_id = "run_terminal02"
            jsonl_path = root / "runs" / run_id / "journal.jsonl"
            _write_jsonl(
                jsonl_path,
                [
                    _row(
                        1,
                        "AgentRunStarted",
                        {"agent_role": "agt_x", "objective": "q"},
                    ),
                    _row(
                        2,
                        "AgentRunFinished",
                        {"agent_role": "agt_x", "ok": True},
                    ),
                ],
            )
            session = _make_session(
                run_id=run_id, jsonl_path=jsonl_path, status=RunStatus.COMPLETED
            )

            _record_terminal_materialization(session)

            latest = root / "latest.json"
            self.assertTrue(latest.exists(), "latest.json must exist")
            latest_payload = json.loads(latest.read_text(encoding="utf-8"))
            self.assertEqual(latest_payload["kind"], "run_pointer")
            self.assertEqual(latest_payload["run_id"], run_id)
            # 临时文件不应残留
            leftovers = list(root.glob("latest.json.tmp-*"))
            self.assertEqual(leftovers, [], "tmp files must not remain after rename")

    def test_session_without_locator_falls_back_to_path_inferred_locator(self) -> None:
        """测试 / 直构造的 session 没 locator;从 jsonl_path 上溯推断 FilesystemRunLocator。"""
        with self._fresh_root() as root:
            run_id = "run_terminal03"
            jsonl_path = root / "runs" / run_id / "journal.jsonl"
            _write_jsonl(jsonl_path, [_row(1, "AgentRunFinished", {"ok": True})])
            session = RunSession(
                run_id=run_id,
                trace_id="t",
                jsonl_path=jsonl_path,
                tail=LiveTail(),
                question="q",
                user_text="q",
                mode="solo",
                agent=parse_agent_ref({"id": "solo", "name": "助手"}),
                status=RunStatus.COMPLETED,
                started_at=1.0,
                closed_at=2.0,
                # locator=None —— 推断路径
            )
            _record_terminal_materialization(session)
            self.assertTrue((root / "runs" / run_id / "manifest.json").exists())

    def test_terminal_event_seq_picks_finished(self) -> None:
        with self._fresh_root() as root:
            run_id = "run_terminal04"
            jsonl_path = root / "runs" / run_id / "journal.jsonl"
            _write_jsonl(
                jsonl_path,
                [
                    _row(1, "AgentRunStarted", {}),
                    _row(7, "AgentRunFinished", {}),
                ],
            )
            session = _make_session(
                run_id=run_id, jsonl_path=jsonl_path, status=RunStatus.COMPLETED
            )
            _record_terminal_materialization(session)
            payload = json.loads(
                (root / "runs" / run_id / "manifest.json").read_text(encoding="utf-8")
            )
            # ADR-0096 I7: scan journal for the terminal event's seq, not event_id.
            self.assertEqual(payload["terminal_event_seq"], 7)
            self.assertNotIn("terminal_event_id", payload)
            self.assertEqual(payload["ledger_high_watermark"], 7)

    def test_terminal_event_seq_fallback_accepts_run_finished(self) -> None:
        with self._fresh_root() as root:
            run_id = "run_terminal_fallback"
            jsonl_path = root / "runs" / run_id / "journal.jsonl"
            terminal = _row(3, "RunFinished", {"ok": True})
            terminal["event_id"] = "evt-run-finished"
            _write_jsonl(jsonl_path, [_row(1, "AgentRunStarted", {}), terminal])
            session = _make_session(
                run_id=run_id, jsonl_path=jsonl_path, status=RunStatus.COMPLETED
            )

            _record_terminal_materialization(session)

            payload = json.loads(
                (root / "runs" / run_id / "manifest.json").read_text(encoding="utf-8")
            )
            # ADR-0096 I7: derived view holds journal seq, not hard event_id.
            self.assertEqual(payload["terminal_event_seq"], 3)
            self.assertNotIn("terminal_event_id", payload)

    def test_v2_envelope_fallback_preserves_watermark_and_terminal_event(self) -> None:
        with self._fresh_root() as root:
            run_id = "run_terminal_v2"
            jsonl_path = root / "runs" / run_id / "journal.jsonl"
            _write_jsonl(
                jsonl_path,
                [
                    {
                        "schema": JOURNAL_SCHEMA_VERSION,
                        "event_id": "evt-v2-finished",
                        "run_id": run_id,
                        "run_seq": 7,
                        "occurred_at": 7.0,
                        "committed_at": 7.0,
                        "scope": {
                            "trace_id": "t",
                            "run_id": run_id,
                            "agent_role": "agt_x",
                            "step": 0,
                        },
                        "causation": {"parent_event_id": "", "links": []},
                        "descriptor": {
                            "type": "AgentRunFinished",
                            "version": 1,
                            "payload_schema_version": 1,
                        },
                        "data": {"status": "completed", "output_text": "done", "error": ""},
                        "evidence": [],
                    }
                ],
            )
            session = _make_session(
                run_id=run_id, jsonl_path=jsonl_path, status=RunStatus.COMPLETED
            )

            _record_terminal_materialization(session)

            payload = json.loads(
                (root / "runs" / run_id / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(payload["ledger_high_watermark"], 7)
            # ADR-0096 I7: derived view holds journal seq, not hard event_id.
            self.assertEqual(payload["terminal_event_seq"], 7)
            self.assertNotIn("terminal_event_id", payload)

    def test_failure_does_not_propagate(self) -> None:
        """任何 IO 错误必须 swallow + 记日志,不能污染 run 关闭。"""
        with self._fresh_root() as root:
            run_id = "run_terminal05"
            jsonl_path = root / "runs" / run_id / "journal.jsonl"
            session = RunSession(
                run_id=run_id,
                trace_id="t",
                jsonl_path=jsonl_path,  # 不存在
                tail=LiveTail(),
                question="q",
                user_text="q",
                mode="solo",
                agent=parse_agent_ref({"id": "solo", "name": "助手"}),
                status=RunStatus.FAILED,
                locator=FilesystemRunLocator(root=root),
            )
            # 不抛
            _record_terminal_materialization(session)
            # journal 不存在 → manifest.json 不写(找不到 ledger_summary / watermark),
            # latest.json 也不更新 —— 因为 manifest_path.parent.mkdir(parents=True) + 写失败
            # 我们只要求不抛
            self.assertTrue(True)

    def test_diagnose_works_on_existing_journal(self) -> None:
        """smoke:``diagnose`` 与新 jsonl 路径兼容(doctor_report 形状)。"""
        with self._fresh_root() as root:
            run_id = "run_terminal06"
            jsonl_path = root / "runs" / run_id / "journal.jsonl"
            _write_jsonl(
                jsonl_path,
                [
                    _row(1, "AgentRunStarted", {}),
                    _row(2, "AgentRunFinished", {}),
                ],
            )
            session = _make_session(
                run_id=run_id, jsonl_path=jsonl_path, status=RunStatus.COMPLETED
            )
            report = diagnose(session, jsonl_path)
            self.assertEqual(report.schema, "doctor.v2")
            self.assertEqual(report.run_id, run_id)
            self.assertGreaterEqual(report.hops["H2"].ok, True)  # type: ignore[arg-type]

    @staticmethod
    def _fresh_root():
        """返回 ``with`` 上下文管理器;退出时清理 tmp。"""

        import tempfile

        class _C:
            def __enter__(self) -> Path:
                self._tmp = tempfile.TemporaryDirectory()
                self._root = Path(self._tmp.__enter__())
                return self._root

            def __exit__(self, *exc: object) -> None:
                self._tmp.__exit__(None, None, None)

        return _C()


if __name__ == "__main__":
    unittest.main()
