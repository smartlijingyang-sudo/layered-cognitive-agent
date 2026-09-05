"""迁移脚本测试 —— ADR-0065 PR-11。

``scripts/migrate_traces_flat_to_v2_layout.py`` 把 ``traces/runs/<id>.jsonl``
+ ``<id>.doctor.json`` 一次性挪进 ``<root>/runs/<id>/``:

- ``<id>.jsonl``        → ``<id>/journal.jsonl``
- ``<id>.doctor.json``  → 合并进 ``<id>/manifest.json`` 的 ``extra.doctor_report``

测试只验证纯函数 + 文件系统副作用;不依赖 gateway 启动。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.migrate_traces_flat_to_v2_layout import (
    _build_plan,
    _execute_plan,
    _ledger_high_watermark_for,
    _ledger_summary_for,
    _scan_flat_artifacts,
    _terminal_event_seq_for,
)


def _fresh_root() -> tuple[Path, tempfile.TemporaryDirectory]:
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    (root / "runs").mkdir()
    return root, tmp


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


class ScanFlatArtifacts(unittest.TestCase):
    def test_picks_up_jsonl_and_doctor_json(self) -> None:
        root, tmp = _fresh_root()
        try:
            (root / "runs" / "run_aaa1.jsonl").write_text("{}", encoding="utf-8")
            (root / "runs" / "run_aaa1.doctor.json").write_text("{}", encoding="utf-8")
            (root / "runs" / "run_bbb2.jsonl").write_text("{}", encoding="utf-8")
            (root / "runs" / "run_bbb2.diagnostic.jsonl").write_text("{}", encoding="utf-8")
            arts = _scan_flat_artifacts(root / "runs")
            run_ids = {(a.run_id, a.suffix) for a in arts}
            self.assertIn(("run_aaa1", ".jsonl"), run_ids)
            self.assertIn(("run_aaa1", ".doctor.json"), run_ids)
            self.assertIn(("run_bbb2", ".jsonl"), run_ids)
            self.assertIn(("run_bbb2", ".diagnostic.jsonl"), run_ids)
        finally:
            tmp.cleanup()

    def test_ignores_unrelated_files(self) -> None:
        root, tmp = _fresh_root()
        try:
            (root / "runs" / "README.txt").write_text("hi", encoding="utf-8")
            (root / "runs" / "notes.md").write_text("# hi", encoding="utf-8")
            (root / "runs" / "run_bad-name.jsonl").write_text("{}", encoding="utf-8")
            arts = _scan_flat_artifacts(root / "runs")
            self.assertEqual(arts, [])
        finally:
            tmp.cleanup()

    def test_skips_directories(self) -> None:
        root, tmp = _fresh_root()
        try:
            (root / "runs" / "run_aaa1").mkdir()
            (root / "runs" / "run_aaa1" / "journal.jsonl").write_text("{}", encoding="utf-8")
            arts = _scan_flat_artifacts(root / "runs")
            self.assertEqual(arts, [])
        finally:
            tmp.cleanup()


class LedgerMetadataExtractors(unittest.TestCase):
    def test_high_watermark_picks_max_seq(self) -> None:
        root, tmp = _fresh_root()
        try:
            path = root / "j.jsonl"
            _write_jsonl(
                path,
                [
                    {"seq": 1, "event_type": "AgentRunStarted", "scope": {}},
                    {"seq": 7, "event_type": "ToolInvoked", "scope": {}},
                    {"seq": 4, "event_type": "ReasoningDone", "scope": {}},
                ],
            )
            self.assertEqual(_ledger_high_watermark_for(path), 7)
        finally:
            tmp.cleanup()

    def test_high_watermark_empty(self) -> None:
        root, tmp = _fresh_root()
        try:
            self.assertEqual(_ledger_high_watermark_for(root / "missing.jsonl"), 0)
        finally:
            tmp.cleanup()

    def test_terminal_event_seq_finds_last_finished(self) -> None:
        root, tmp = _fresh_root()
        try:
            path = root / "j.jsonl"
            _write_jsonl(
                path,
                [
                    {"seq": 1, "event_type": "AgentRunStarted", "scope": {"event_id": "started1"}},
                    {
                        "seq": 2,
                        "event_type": "AgentRunFinished",
                        "scope": {"event_id": "finished2"},
                    },
                    {
                        "seq": 3,
                        "event_type": "AgentRunFinished",
                        "scope": {"event_id": "finished3"},
                    },
                ],
            )
            # ADR-0096 I7: derived view holds journal seq, not hard event_id.
            self.assertEqual(_terminal_event_seq_for(path), 3)
        finally:
            tmp.cleanup()

    def test_ledger_summary_deterministic(self) -> None:
        root, tmp = _fresh_root()
        try:
            path = root / "j.jsonl"
            _write_jsonl(path, [{"seq": 1}, {"seq": 2}])
            s1 = _ledger_summary_for(path)
            s2 = _ledger_summary_for(path)
            self.assertEqual(s1, s2)
            self.assertEqual(len(s1), 64)
        finally:
            tmp.cleanup()


class PlanAndExecute(unittest.TestCase):
    def test_dry_run_does_not_move_files(self) -> None:
        root, tmp = _fresh_root()
        try:
            journal = root / "runs" / "run_aaa1.jsonl"
            doctor = root / "runs" / "run_aaa1.doctor.json"
            journal.write_text("{}", encoding="utf-8")
            doctor.write_text(json.dumps({"schema": "doctor.v2", "ok": True}), encoding="utf-8")
            plan = _build_plan(
                root=root,
                artifacts=_scan_flat_artifacts(root / "runs"),
            )
            self.assertEqual(len(plan.journal_moves), 1)
            self.assertEqual(len(plan.manifest_writes), 1)
            self.assertTrue(journal.exists())
            self.assertTrue(doctor.exists())
        finally:
            tmp.cleanup()

    def test_apply_moves_journal_and_writes_manifest(self) -> None:
        root, tmp = _fresh_root()
        try:
            (root / "runs" / "run_aaa1.jsonl").write_text(
                "\n".join(
                    json.dumps(r)
                    for r in [
                        {"seq": 1, "event_type": "AgentRunStarted", "scope": {}},
                        {"seq": 2, "event_type": "AgentRunFinished", "scope": {"event_id": "fin1"}},
                    ]
                ),
                encoding="utf-8",
            )
            (root / "runs" / "run_aaa1.doctor.json").write_text(
                json.dumps({"schema": "doctor.v2", "summary": "ok"}),
                encoding="utf-8",
            )

            arts = _scan_flat_artifacts(root / "runs")
            plan = _build_plan(root=root, artifacts=arts)
            counts = _execute_plan(root=root, plan=plan)

            self.assertEqual(counts["journal_moved"], 1)
            self.assertEqual(counts["manifest_written"], 1)

            run_dir = root / "runs" / "run_aaa1"
            self.assertTrue((run_dir / "journal.jsonl").exists())
            self.assertTrue((run_dir / "manifest.json").exists())

            self.assertFalse((root / "runs" / "run_aaa1.jsonl").exists())
            self.assertFalse((root / "runs" / "run_aaa1.doctor.json").exists())

            payload = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["run_id"], "run_aaa1")
            self.assertEqual(payload["ledger_high_watermark"], 2)
            # ADR-0096 I7: derived view holds journal seq, not hard event_id.
            self.assertEqual(payload["terminal_event_seq"], 2)
            self.assertNotIn("terminal_event_id", payload)
            self.assertEqual(payload["extra"]["doctor_report"]["summary"], "ok")
            self.assertIn("migrated_from", payload["extra"])
        finally:
            tmp.cleanup()

    def test_idempotent_skips_already_migrated(self) -> None:
        root, tmp = _fresh_root()
        try:
            (root / "runs" / "run_aaa1").mkdir()
            (root / "runs" / "run_aaa1" / "journal.jsonl").write_text("{}", encoding="utf-8")
            (root / "runs" / "run_aaa1.jsonl").write_text("{}", encoding="utf-8")
            plan = _build_plan(
                root=root,
                artifacts=_scan_flat_artifacts(root / "runs"),
            )
            self.assertIn("run_aaa1", plan.skipped_existing_dirs)
            self.assertEqual(len(plan.journal_moves), 0)
        finally:
            tmp.cleanup()

    def test_orphan_flat_files_are_left_alone(self) -> None:
        root, tmp = _fresh_root()
        try:
            (root / "runs" / "run_orphan1.doctor.json").write_text("{}", encoding="utf-8")
            plan = _build_plan(
                root=root,
                artifacts=_scan_flat_artifacts(root / "runs"),
            )
            self.assertEqual(len(plan.journal_moves), 0)
            self.assertEqual(len(plan.skipped_unrelated), 1)
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
