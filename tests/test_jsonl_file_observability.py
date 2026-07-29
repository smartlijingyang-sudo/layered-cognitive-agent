"""Unit tests for JSONLFileObservability + hook span attribute extraction."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from lca.contracts.observability import TraceSpan
from lca.layer0_infra.observability.jsonl_file_observability import JSONLFileObservability


class TestJSONLFileObservability(unittest.TestCase):
    """Tests for JSONLFileObservability."""

    def test_emit_span_creates_file(self) -> None:
        """emit_span creates the output file if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "subdir" / "trace.jsonl"
            obs = JSONLFileObservability(output_path=output)
            span = TraceSpan(
                span_id="span_001",
                trace_id="trace_001",
                name="test_span",
                started_at=datetime.now(timezone.utc),
            )
            obs.emit_span(span)
            self.assertTrue(output.is_file())

    def test_emit_span_writes_valid_json(self) -> None:
        """Each span is written as a valid JSON line."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "trace.jsonl"
            obs = JSONLFileObservability(output_path=output)
            span = TraceSpan(
                span_id="span_002",
                trace_id="trace_001",
                name="hook.post_think",
                started_at=datetime.now(timezone.utc),
                attributes={"action_type": "respond", "confidence": 0.95},
            )
            obs.emit_span(span)
            lines = output.read_text(encoding="utf-8").strip().split("\n")
            self.assertEqual(len(lines), 1)
            record = json.loads(lines[0])
            self.assertEqual(record["span_id"], "span_002")
            self.assertEqual(record["attributes"]["action_type"], "respond")

    def test_multiple_spans_append(self) -> None:
        """Multiple spans are appended, one per line."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "trace.jsonl"
            obs = JSONLFileObservability(output_path=output)
            for i in range(3):
                span = TraceSpan(
                    span_id=f"span_{i:03d}",
                    trace_id="trace_001",
                    name=f"step_{i}",
                    started_at=datetime.now(timezone.utc),
                )
                obs.emit_span(span)
            lines = output.read_text(encoding="utf-8").strip().split("\n")
            self.assertEqual(len(lines), 3)

    def test_datetime_serialized_as_iso(self) -> None:
        """Datetime fields are serialized as ISO format strings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "trace.jsonl"
            obs = JSONLFileObservability(output_path=output)
            now = datetime.now(timezone.utc)
            span = TraceSpan(
                span_id="span_dt",
                trace_id="trace_dt",
                name="test",
                started_at=now,
            )
            obs.emit_span(span)
            record = json.loads(output.read_text(encoding="utf-8").strip())
            # Should be a valid ISO string, not a Python datetime repr
            self.assertIsInstance(record["started_at"], str)
            self.assertIn("T", record["started_at"])


class TestHookSpanAttributes(unittest.TestCase):
    """Tests for extract_span_attributes and redaction utilities."""

    def test_extract_decision_attributes(self) -> None:
        """post_think kwargs with decision extracts action_type and confidence."""
        from lca.layer0_infra.observability.span_attributes import extract_span_attributes

        class FakeDecision:
            action_type = "respond"
            confidence = 0.9
            response_text = "这是回答"
            tool_name = None

        attrs = extract_span_attributes("post_think", {"decision": FakeDecision()})
        self.assertEqual(attrs["action_type"], "respond")
        self.assertEqual(attrs["confidence"], 0.9)
        self.assertIn("这是回答", attrs["response_preview"])

    def test_extract_error_attributes(self) -> None:
        """on_error kwargs extracts error type and message."""
        from lca.layer0_infra.observability.span_attributes import extract_span_attributes

        attrs = extract_span_attributes("on_error", {"error": ValueError("bad input")})
        self.assertEqual(attrs["error_type"], "ValueError")
        self.assertEqual(attrs["error_message"], "bad input")

    def test_sanitize_secrets(self) -> None:
        """Secret-like patterns are redacted."""
        from lca.layer0_infra.observability.redaction import sanitize

        self.assertNotIn("sk-1234567890abcdef", sanitize("key=sk-1234567890abcdef"))
        self.assertIn("[REDACTED]", sanitize("key=sk-1234567890abcdef"))

    def test_truncate_long_text(self) -> None:
        """Long text is truncated."""
        from lca.layer0_infra.observability.redaction import truncate

        long_text = "a" * 500
        result = truncate(long_text)
        self.assertLessEqual(len(result), 203)  # 200 + "..."
        self.assertTrue(result.endswith("..."))


if __name__ == "__main__":
    unittest.main()
