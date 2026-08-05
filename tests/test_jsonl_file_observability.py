"""Unit tests for JsonlExporter + hook span attribute extraction + redaction."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lca.contracts.telemetry import SpanName
from lca.layer0_infra.observability import ObservabilityHub, bind, span
from lca.layer0_infra.observability.exporters.jsonl import JsonlExporter


def _jsonl_hub(tmpdir: str, filename: str = "trace.jsonl") -> tuple[ObservabilityHub, Path]:
    output = Path(tmpdir) / filename
    return ObservabilityHub([JsonlExporter(output)]), output


def _span_records(output: Path) -> list[dict]:
    lines = output.read_text(encoding="utf-8").strip().split("\n")
    records = [json.loads(line) for line in lines if line.strip()]
    return [r for r in records if r.get("record") == "span"]


class TestJsonlExporter(unittest.TestCase):
    """Tests for JsonlExporter through the real hub pipeline."""

    def test_emit_span_creates_file(self) -> None:
        """export creates the output file (incl. missing parents) if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "subdir" / "trace.jsonl"
            hub = ObservabilityHub([JsonlExporter(target)])
            with bind(hub), span(SpanName.RUN_AGENT):
                pass
            self.assertTrue(target.is_file())

    def test_emit_span_writes_valid_json(self) -> None:
        """Each span is written as a valid JSON line with record=span."""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, output = _jsonl_hub(tmpdir)
            with (
                bind(hub),
                span(
                    SpanName.LOOP_PHASE_THINK,
                    **{"action_type": "respond", "confidence": 0.95},
                ),
            ):
                pass
            records = _span_records(output)
            self.assertEqual(len(records), 1)
            record = records[0]
            self.assertEqual(record["name"], SpanName.LOOP_PHASE_THINK.value)
            self.assertEqual(record["attributes"]["action_type"], "respond")

    def test_multiple_spans_append(self) -> None:
        """Multiple spans are appended, one per line."""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, output = _jsonl_hub(tmpdir)
            with bind(hub):
                for i in range(3):
                    with span(SpanName.TOOL_EXECUTE, **{"i": i}):
                        pass
            records = _span_records(output)
            self.assertEqual(len(records), 3)

    def test_record_schema_fields(self) -> None:
        """Span records carry topology + timing fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, output = _jsonl_hub(tmpdir)
            with bind(hub), span(SpanName.RUN_AGENT):
                pass
            record = _span_records(output)[0]
            for key in ("trace_id", "span_id", "parent_span_id", "status", "duration_ms"):
                self.assertIn(key, record)


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
