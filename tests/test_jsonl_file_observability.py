"""journal jsonl 落盘 + hook 属性提取 + 脱敏守卫（ADR-0037 journal.v1 schema）。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from lca.infrastructure.observability.settings import ObservabilitySettings

from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    AgentRunStarted,
    RunScope,
    TeamRunFinished,
    TeamRunStarted,
    run_scope,
)
from lca.harness.observability import make_minimal_bound
from lca.infrastructure.observability import (
    AttributePolicy,
    BoundObservability,
    RunStore,
    bind_backends,
    record,
)
from lca.infrastructure.observability.journal.engine.journal_io import (
    JOURNAL_SCHEMA_VERSION,
    load_journal_records,
    read_journal,
)
from lca.infrastructure.observability.journal.jsonl.projector import JsonlJournalProjector


def _journal_hub(tmpdir: str, filename: str = "journal.jsonl") -> tuple[BoundObservability, Path]:
    output = Path(tmpdir) / filename
    cfg = ObservabilitySettings(backends="jsonl", jsonl_path=str(output))
    # Construct BoundObservability directly with a JsonlJournalProjector.
    policy = AttributePolicy(verbosity=cfg.verbosity, redact=cfg.redact_enabled)
    projections: tuple[Any, ...] = (JsonlJournalProjector(output),)
    store = RunStore(policy=policy, projections=projections)
    return make_minimal_bound(journal=store, policy=policy), output


def _run_solo(bound: BoundObservability) -> None:
    scope = RunScope(trace_id="t", run_id="r", agent_role="Solo")
    with bind_backends(bound), run_scope(scope):
        record(AgentRunStarted(agent_role="Solo", objective="hi"))
        record(AgentRunFinished(status="completed", steps=1, output_text="done"))


class TestJsonlJournalProjector(unittest.TestCase):
    """journal 落盘：schema 版本化、indent=2 JSON、replay 可重建。"""

    def test_creates_file_including_missing_parents(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "subdir" / "journal.jsonl"
            cfg = ObservabilitySettings(backends="jsonl", jsonl_path=str(target))
            policy = AttributePolicy(verbosity=cfg.verbosity, redact=cfg.redact_enabled)
            store = RunStore(policy=policy, projections=(JsonlJournalProjector(target),))
            bound = make_minimal_bound(journal=store, policy=policy)
            _run_solo(bound)
            store.close()
            self.assertTrue(target.is_file())

    def test_writes_schema_versioned_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, output = _journal_hub(tmpdir)
            _run_solo(hub)
            if hub.journal is not None:
                hub.journal.close()
            records = load_journal_records(output)
            self.assertGreaterEqual(len(records), 2)
            for record in records:
                self.assertEqual(record["schema"], JOURNAL_SCHEMA_VERSION)
                self.assertIn("scope", record)
                self.assertIn("descriptor", record)
                self.assertEqual(record["descriptor"]["type"], record["descriptor"]["type"])
            types = {x["descriptor"]["type"] for x in records}
            self.assertIn("AgentRunStarted", types)
            self.assertIn("AgentRunFinished", types)

    def test_scope_carries_correlation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, output = _journal_hub(tmpdir)
            _run_solo(hub)
            hub.journal.close() if hub.journal else None
            first = load_journal_records(output)[0]
            scope = first["scope"]
            self.assertEqual(scope["trace_id"], "t")
            self.assertEqual(scope["run_id"], "r")
            self.assertEqual(scope["agent_role"], "Solo")

    def test_replay_reconstructs_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, output = _journal_hub(tmpdir)
            scope = RunScope(trace_id="t", run_id="team-run")
            with bind_backends(hub), run_scope(scope):
                record(TeamRunStarted(team_id="team-x", strategy_key="lead"))
                record(TeamRunFinished(status="completed", steps=1))
            hub.journal.close() if hub.journal else None
            events = read_journal(output)
            self.assertEqual(len(events), 2)
            self.assertIsInstance(events[0].event, TeamRunStarted)
            self.assertEqual(events[0].event.team_id, "team-x")
            self.assertEqual(events[0].scope.run_id, "team-run")
            self.assertIsInstance(events[1].event, TeamRunFinished)

    def test_disk_records_are_pretty_printed_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, output = _journal_hub(tmpdir)
            _run_solo(hub)
            if hub.journal is not None:
                hub.journal.close()
            text = output.read_text(encoding="utf-8")
            self.assertIn('\n  "schema":', text)
            self.assertGreaterEqual(len(load_journal_records(output)), 2)

    def test_nested_runtime_attributes_stay_json_objects(self) -> None:
        from lca.infrastructure.observability import record_runtime

        with tempfile.TemporaryDirectory() as tmpdir:
            hub, output = _journal_hub(tmpdir)
            scope = RunScope(trace_id="t", run_id="r", agent_role="Solo")
            with bind_backends(hub), run_scope(scope):
                record_runtime(
                    "journal",
                    "phase.fact",
                    plugin="perceive.main",
                    attributes={
                        "payload": {
                            "node": "perceive.main",
                            "semantic_phase": "perceive",
                        }
                    },
                )
            if hub.journal is not None:
                hub.journal.close()
            records = load_journal_records(output)
            self.assertGreaterEqual(len(records), 1)
            payload = records[0]["data"]["attributes"]["payload"]
            self.assertEqual(
                payload,
                {"node": "perceive.main", "semantic_phase": "perceive"},
            )
            text = output.read_text(encoding="utf-8")
            self.assertIn('\n        "node": "perceive.main"', text)

    def test_read_journal_accepts_compact_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "compact.jsonl"
            compact = {
                "schema": JOURNAL_SCHEMA_VERSION,
                "event_id": "01TESTCOMPACTJSONL0000000000",
                "run_id": "r",
                "run_seq": 1,
                "occurred_at": 1.0,
                "committed_at": 1.0,
                "scope": {
                    "trace_id": "t",
                    "run_id": "r",
                    "parent_run_id": None,
                    "parent_trace_id": None,
                    "delegation_id": None,
                    "agent_role": "Solo",
                    "step": 0,
                },
                "causation": {"parent_event_id": "", "links": []},
                "descriptor": {
                    "type": "AgentRunStarted",
                    "version": 1,
                    "payload_schema_version": 1,
                },
                "data": {
                    "agent_role": "Solo",
                    "strategy_key": "solo",
                    "objective": "hi",
                    "from_role": "",
                },
                "evidence": [],
                "plan_ref": "",
            }
            path.write_text(json.dumps(compact, ensure_ascii=False) + "\n", encoding="utf-8")
            events = read_journal(path)
            self.assertEqual(len(events), 1)
            self.assertIsInstance(events[0].event, AgentRunStarted)


class TestHookSpanAttributes(unittest.TestCase):
    """Tests for hook attribute extraction and redaction utilities."""

    def test_extract_decision_attributes(self) -> None:
        """post_think kwargs with decision extracts action_type and confidence."""
        from lca.cognition.hook_registry import _extract_span_attributes

        class FakeDecision:
            action_type = "respond"
            confidence = 0.9
            response_text = "这是回答"
            tool_name = None

        attrs = _extract_span_attributes("post_think", {"decision": FakeDecision()})
        self.assertEqual(attrs["action_type"], "respond")
        self.assertEqual(attrs["confidence"], 0.9)
        self.assertIn("这是回答", attrs["response_preview"])

    def test_extract_error_attributes(self) -> None:
        """on_error kwargs extracts error type and message."""
        from lca.cognition.hook_registry import _extract_span_attributes

        attrs = _extract_span_attributes("on_error", {"error": ValueError("bad input")})
        self.assertEqual(attrs["error_type"], "ValueError")
        self.assertEqual(attrs["error_message"], "bad input")

    def test_sanitize_secrets(self) -> None:
        """Secret-like patterns are redacted."""
        from lca.infrastructure.observability.policy import sanitize

        self.assertNotIn("sk-1234567890abcdef", sanitize("key=sk-1234567890abcdef"))
        self.assertIn("[REDACTED]", sanitize("key=sk-1234567890abcdef"))

    def test_truncate_long_text(self) -> None:
        """Long text is truncated."""
        from lca.infrastructure.observability.policy import truncate

        long_text = "a" * 500
        result = truncate(long_text, 200)
        self.assertLessEqual(len(result), 203)  # 200 + "..."
        self.assertTrue(result.endswith("..."))


if __name__ == "__main__":
    unittest.main()
