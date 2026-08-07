"""journal jsonl 落盘 + hook 属性提取 + 脱敏守卫（ADR-0037 journal.v1 schema）。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    AgentRunStarted,
    RunScope,
    TeamRunFinished,
    TeamRunStarted,
    run_scope,
)
from lca.layer0_infra.observability import ObservabilityHub, bind, create_observability, record
from lca.layer0_infra.observability.journal.journal_io import (
    JOURNAL_SCHEMA_VERSION,
    read_journal,
)
from lca.layer0_infra.observability.settings import ObservabilitySettings


def _journal_hub(tmpdir: str, filename: str = "journal.jsonl") -> tuple[ObservabilityHub, Path]:
    output = Path(tmpdir) / filename
    cfg = ObservabilitySettings(backends="jsonl", jsonl_path=str(output))
    return create_observability("jsonl", settings=cfg), output


def _run_solo(hub: ObservabilityHub) -> None:
    scope = RunScope(trace_id="t", run_id="r", agent_role="Solo")
    with bind(hub), run_scope(scope):
        record(AgentRunStarted(agent_role="Solo", objective="hi"))
        record(AgentRunFinished(status="completed", steps=1, output_text="done"))


class TestJsonlJournalProjector(unittest.TestCase):
    """journal 落盘：schema 版本化、一行一事件、replay 可重建。"""

    def test_creates_file_including_missing_parents(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "subdir" / "journal.jsonl"
            cfg = ObservabilitySettings(backends="jsonl", jsonl_path=str(target))
            hub = create_observability("jsonl", settings=cfg)
            _run_solo(hub)
            hub.close()
            self.assertTrue(target.is_file())

    def test_writes_schema_versioned_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, output = _journal_hub(tmpdir)
            _run_solo(hub)
            hub.close()
            lines = [json.loads(x) for x in output.read_text(encoding="utf-8").splitlines() if x]
            self.assertGreaterEqual(len(lines), 2)
            for line in lines:
                self.assertEqual(line["schema"], JOURNAL_SCHEMA_VERSION)
                self.assertIn("scope", line)
                self.assertIn("event_type", line)
                self.assertIn("event", line)
            types = {x["event_type"] for x in lines}
            self.assertIn("AgentRunStarted", types)
            self.assertIn("AgentRunFinished", types)

    def test_scope_carries_correlation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, output = _journal_hub(tmpdir)
            _run_solo(hub)
            hub.close()
            first = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
            scope = first["scope"]
            self.assertEqual(scope["trace_id"], "t")
            self.assertEqual(scope["run_id"], "r")
            self.assertEqual(scope["agent_role"], "Solo")

    def test_replay_reconstructs_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, output = _journal_hub(tmpdir)
            scope = RunScope(trace_id="t", run_id="team-run")
            with bind(hub), run_scope(scope):
                record(TeamRunStarted(team_id="team-x", strategy_key="lead"))
                record(TeamRunFinished(status="completed", steps=1))
            hub.close()
            events = read_journal(output)
            self.assertEqual(len(events), 2)
            self.assertIsInstance(events[0].event, TeamRunStarted)
            self.assertEqual(events[0].event.team_id, "team-x")
            self.assertEqual(events[0].scope.run_id, "team-run")
            self.assertIsInstance(events[1].event, TeamRunFinished)


class TestHookSpanAttributes(unittest.TestCase):
    """Tests for hook attribute extraction and redaction utilities."""

    def test_extract_decision_attributes(self) -> None:
        """post_think kwargs with decision extracts action_type and confidence."""
        from lca.layer1_cognitive.hook_registry import _extract_span_attributes

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
        from lca.layer1_cognitive.hook_registry import _extract_span_attributes

        attrs = _extract_span_attributes("on_error", {"error": ValueError("bad input")})
        self.assertEqual(attrs["error_type"], "ValueError")
        self.assertEqual(attrs["error_message"], "bad input")

    def test_sanitize_secrets(self) -> None:
        """Secret-like patterns are redacted."""
        from lca.layer0_infra.observability.policy import sanitize

        self.assertNotIn("sk-1234567890abcdef", sanitize("key=sk-1234567890abcdef"))
        self.assertIn("[REDACTED]", sanitize("key=sk-1234567890abcdef"))

    def test_truncate_long_text(self) -> None:
        """Long text is truncated."""
        from lca.layer0_infra.observability.policy import truncate

        long_text = "a" * 500
        result = truncate(long_text, 200)
        self.assertLessEqual(len(result), 203)  # 200 + "..."
        self.assertTrue(result.endswith("..."))


if __name__ == "__main__":
    unittest.main()
